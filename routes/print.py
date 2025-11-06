from flask import Blueprint, render_template, render_template_string, request, redirect, url_for, session, flash, make_response, send_file
from models import db, Stredisko, Faktura, ZalohovaFaktura, InfoDodavatele, InfoOdberatele, InfoVystavovatele, VypocetOM, OdberneMisto, Odečet, ObdobiFakturace
# Alias pro zpětnou kompatibilitu s kódem bez diakritiky
Odecet = Odečet
from datetime import datetime
import io

from file_helpers import get_faktury_path, get_faktura_filenames, check_faktury_exist

# REPORTLAB IMPORTS - odstraněno, používá se pouze WeasyPrint

# WORKAROUND PRO PYDYF KONFLIKT - použij wkhtmltopdf alternativu
def _safe_weasyprint_convert(html_content):
    """Bezpečná konverze HTML na PDF - workaround pro pydyf problém"""

    # ŘEŠENÍ 1: Zkus WeasyPrint s vyčištěným prostředím
    try:
        import os
        import sys

        # Vyčisti environment pro WeasyPrint
        env = os.environ.copy()
        env.pop('PYTHONPATH', None)

        import weasyprint

        # Zkus základní volání
        weasy_html = weasyprint.HTML(string=html_content, base_url='file://')

        # Zkus s různými parametry
        for attempt in [
            lambda: weasy_html.write_pdf(),
            lambda: weasy_html.write_pdf(optimize_size=False),
            lambda: weasy_html.write_pdf(pdf_version='1.4'),
        ]:
            try:
                return attempt()
            except TypeError as te:
                if "PDF.__init__" in str(te):
                    continue  # Zkus další způsob
                else:
                    raise te

    except Exception as weasy_error:
        pass  # Pokračuj k fallback řešení

    # ŘEŠENÍ 2: Pokud WeasyPrint selže, vrať jednoduchou HTML odpověď s instrukcemi
    fallback_message = f"""
    <h1>PDF Generování Selhalo</h1>
    <p>WeasyPrint má problém s pydyf knihovnou na serveru.</p>
    <p>Chyba: pydyf.PDF argumenty nejsou kompatibilní</p>
    <h2>Řešení:</h2>
    <ol>
        <li>Aktualizovat requirements.txt: pydyf==0.8.0</li>
        <li>Nebo downgrade WeasyPrint na verzi 59.0</li>
        <li>Nebo použít alternativu jako wkhtmltopdf</li>
    </ol>
    <hr>
    <details>
        <summary>HTML obsah faktury</summary>
        <div style="border: 1px solid #ccc; padding: 10px; margin: 10px 0;">
            {html_content}
        </div>
    </details>
    """

    # Vrať HTML místo PDF s chybovou hláškou
    return fallback_message.encode('utf-8')

try:
    import weasyprint
    WEASYPRINT_AVAILABLE = True
    print(f"[INFO] WeasyPrint successfully imported, version: {weasyprint.__version__}")
except ImportError as e:
    WEASYPRINT_AVAILABLE = False
    print(f"[WARNING] WeasyPrint not available: {e}")
except Exception as e:
    WEASYPRINT_AVAILABLE = False
    print(f"[ERROR] WeasyPrint import error: {e}")

# Import kompatibilní verze PDF knihovny - DOČASNĚ VYPNUTO
PDF_VERSION = 'disabled'
PdfReader = None  
PdfWriter = None
print("[WARNING] PyPDF2/pypdf import temporarily disabled for server compatibility")

# Kompatibilní wrapper funkce pro různé verze PDF knihoven
def add_page_to_writer(writer, page):
    """Kompatibilní funkce pro přidání stránky do PdfWriter"""
    if hasattr(writer, 'add_page'):
        writer.add_page(page)  # Nová syntaxe (pypdf, PyPDF2 3.x+)
    elif hasattr(writer, 'addPage'):
        writer.addPage(page)   # Stará syntaxe (PyPDF2 < 3.x)
    else:
        raise Exception("Nepodporovaná verze PDF knihovny")

def write_pdf_to_stream(writer, stream):
    """Kompatibilní funkce pro zápis PDF do streamu"""
    if hasattr(writer, 'write'):
        writer.write(stream)
    elif hasattr(writer, 'writeToFile'):
        writer.writeToFile(stream)  # Možná starší verze
    else:
        raise Exception("Nepodporovaná verze PDF knihovny pro zápis")

def close_pdf_writer(writer):
    """Kompatibilní funkce pro zatvorenie PDF writera"""
    if hasattr(writer, 'close'):
        writer.close()
    # Staršie verzie nemusia mať close() metódu

def create_pdf_reader(stream):
    """Kompatibilní funkce pro vytvorenie PdfReader - robustné řešení pro PyPDF2 3.x"""
    import io
    
    # Uisti sa, že stream je na začiatku
    if hasattr(stream, 'seek'):
        stream.seek(0)
    
    # Získaj data zo streamu
    if isinstance(stream, io.BytesIO):
        data = stream.getvalue()
    elif hasattr(stream, 'read'):
        data = stream.read()
        if hasattr(stream, 'seek'):
            stream.seek(0)  # Reset stream pre prípad ďalšieho použitia
    else:
        raise Exception(f"Nepodporovaný stream typ: {type(stream)}")
    
    # Vytvor nový BytesIO stream s dátami
    clean_stream = io.BytesIO(data)
    
    try:
        # Skús moderný PdfReader (PyPDF2 3.x, pypdf)
        return PdfReader(clean_stream)
    except Exception as e:
        error_msg = str(e).lower()
        if 'takes 1 positional argument' in error_msg or 'positional argument' in error_msg:
            print(f"[ERROR] PyPDF2 verzia má nekompatibilný API: {e}")
            print("[WARNING] PDF čítanie zlyháva kvôli nekompatibilite PyPDF2 3.x")
            # Pokus o fallback s file-like objektom
            try:
                clean_stream.seek(0)
                # Skús bez argumentov (pre niektoré broken builds)
                reader = PdfReader()
                if hasattr(reader, 'stream'):
                    reader.stream = clean_stream
                if hasattr(reader, '_get_object'):
                    return reader
            except:
                pass
            
            raise Exception(f"PyPDF2 {PDF_VERSION} nie je kompatibilný s aktuálnym kódom. Prosím aktualizujte na pypdf alebo downgrade PyPDF2.")
        else:
            print(f"[ERROR] Neočakávaná chyba v create_pdf_reader: {e}")
            raise e 

print_bp = Blueprint("print", __name__, template_folder="templates")

# ============== HELPER FUNKCE ==============

def get_faktura_data(stredisko_id, rok, mesic):
    """Sdílená funkce pro získání dat faktury (pro HTML i PDF)"""
    if not session.get("user_id"):
        return None, redirect("/login")

    stredisko = Stredisko.query.get_or_404(stredisko_id)
    if stredisko.user_id != session["user_id"]:
        return None, ("Nepovolený přístup", 403)

    # Najdi období
    obdobi = ObdobiFakturace.query.filter_by(
        stredisko_id=stredisko_id, rok=rok, mesic=mesic
    ).first_or_404()

    # Načti všechna potřebná data
    faktura = Faktura.query.filter_by(stredisko_id=stredisko_id, obdobi_id=obdobi.id).first()
    zaloha = ZalohovaFaktura.query.filter_by(stredisko_id=stredisko_id, obdobi_id=obdobi.id).first()
    dodavatel = InfoDodavatele.query.filter_by(stredisko_id=stredisko_id).first()
    odberatel = InfoOdberatele.query.filter_by(stredisko_id=stredisko_id).first()
    vystavovatel = InfoVystavovatele.query.filter_by(stredisko_id=stredisko_id).first()
    
    # Načti výpočty pro dané období
    vypocty = VypocetOM.query.filter(VypocetOM.obdobi_id == obdobi.id)\
        .join(OdberneMisto)\
        .filter(OdberneMisto.stredisko_id == stredisko_id)\
        .all()

    if not vypocty:
        return None, ("Nejsou k dispozici výpočty pro vybrané období.", 400)

    # Načti odečty pro výpočet dofakturace/bonus
    odecty = Odecet.query.filter_by(
        stredisko_id=stredisko_id, 
        obdobi_id=obdobi.id
    ).all()

    # Výpočet dofakturace/bonus z odečtů
    suma_slevovy_bonus = float(sum(o.slevovy_bonus or 0 for o in odecty))
    suma_dofakturace = float(sum(o.dofakturace or 0 for o in odecty))
    dofakturace_bonus = suma_dofakturace - suma_slevovy_bonus

    # Zjisti, zda fakturovat jen distribuci nebo ne
    fakturovat_jen_distribuci = faktura.fakturovat_jen_distribuci if faktura else False

    # Sumarizace položek faktury - převeď vše na float
    rekapitulace = {
        'mesicni_plat': float(sum(v.mesicni_plat or 0 for v in vypocty)),
        'elektrinu_vt': float(sum(v.platba_za_elektrinu_vt or 0 for v in vypocty)),
        'elektrinu_nt': float(sum(v.platba_za_elektrinu_nt or 0 for v in vypocty)),
        'systemove_sluzby': float(sum(v.systemove_sluzby or 0 for v in vypocty)),
        'poze_minimum': float(sum(min(v.poze_dle_jistice or 0, v.poze_dle_spotreby or 0) for v in vypocty)),
        'nesitova_infrastruktura': float(sum(v.nesitova_infrastruktura or 0 for v in vypocty)),
        'platba_za_jistic': float(sum(v.platba_za_jistic or 0 for v in vypocty)),
        'distribuce_vt': float(sum(v.platba_za_distribuci_vt or 0 for v in vypocty)),
        'distribuce_nt': float(sum(v.platba_za_distribuci_nt or 0 for v in vypocty)),
        'dan_z_elektriny': float(sum(v.dan_z_elektriny or 0 for v in vypocty)),
        'dofakturace_bonus': dofakturace_bonus,  # [OK] DOFAKTURACE/BONUS
    }

    sazba_dph = float(faktura.sazba_dph / 100) if faktura and faktura.sazba_dph else 0.21

    # Použij předpočítané hodnoty z databáze pokud jsou k dispozici a fakturujeme jen distribuci
    if fakturovat_jen_distribuci and vypocty and hasattr(vypocty[0], 'zaklad_bez_dph_bez_di'):
        # Použij předpočítané hodnoty jen distribuce z databáze
        zaklad_bez_dph = float(sum(v.zaklad_bez_dph_bez_di or 0 for v in vypocty))
        castka_dph = float(sum(v.castka_dph_bez_di or 0 for v in vypocty))
        celkem_vc_dph = float(sum(v.celkem_vc_dph_bez_di or 0 for v in vypocty))
    else:
        # Standardní výpočet (kompletní faktura)
        zaklad_bez_dph = float(sum(rekapitulace.values()))
        castka_dph = zaklad_bez_dph * sazba_dph
        celkem_vc_dph = zaklad_bez_dph + castka_dph
    
    # Záloha - hodnota je už s DPH
    if zaloha and zaloha.zaloha:
        zaloha_celkem_vc_dph = float(zaloha.zaloha)
        zaloha_hodnota = zaloha_celkem_vc_dph / (1 + sazba_dph)
        zaloha_dph = zaloha_celkem_vc_dph - zaloha_hodnota
    else:
        zaloha_celkem_vc_dph = 0
        zaloha_hodnota = 0
        zaloha_dph = 0

    k_platbe = celkem_vc_dph - zaloha_celkem_vc_dph
    sazba_dph_procenta = int(sazba_dph * 100)

    return {
        'stredisko': stredisko,
        'obdobi': obdobi,
        'faktura': faktura,
        'zaloha': zaloha,
        'dodavatel': dodavatel,
        'odberatel': odberatel,
        'vystavovatel': vystavovatel,
        'rekapitulace': rekapitulace,
        'zaklad_bez_dph': zaklad_bez_dph,
        'castka_dph': castka_dph,
        'celkem_vc_dph': celkem_vc_dph,
        'zaloha_celkem_vc_dph': zaloha_celkem_vc_dph,
        'zaloha_hodnota': zaloha_hodnota,
        'zaloha_dph': zaloha_dph,
        'k_platbe': k_platbe,
        'sazba_dph': sazba_dph,
        'sazba_dph_procenta': sazba_dph_procenta,
        'suma_slevovy_bonus': suma_slevovy_bonus,
        'suma_dofakturace': suma_dofakturace,
        'dofakturace_bonus': dofakturace_bonus
    }, None

def register_czech_fonts():
    """Registruje fonty s plnou podporou českých znaků"""
    try:
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.pdfbase import pdfmetrics
        import os
        
        # [OK] ROZŠÍŘENÝ SEZNAM FONTŮ S ČESKOU PODPOROU
        font_paths = [
            # Windows fonty s plnou českou podporou
            'C:/Windows/Fonts/arial.ttf',
            'C:/Windows/Fonts/arialbd.ttf',  # Arial Bold
            'C:/Windows/Fonts/calibri.ttf',
            'C:/Windows/Fonts/calibrib.ttf',  # Calibri Bold
            'C:/Windows/Fonts/tahoma.ttf',   # Tahoma má výbornou českOU podporu
            'C:/Windows/Fonts/tahomabd.ttf', # Tahoma Bold
            'C:/Windows/Fonts/verdana.ttf',  # Verdana
            'C:/Windows/Fonts/verdanab.ttf', # Verdana Bold
            
            # macOS fonty
            '/System/Library/Fonts/Arial.ttf',
            '/System/Library/Fonts/Helvetica.ttc',
            
            # Linux fonty s českou podporou
            '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
            '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
            '/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf',
        ]
        
        font_registered = False
        
        # Zkus registrovat první dostupný font
        for font_path in font_paths:
            if os.path.exists(font_path):
                try:
                    # [OK] REGISTRUJ ZÁKLADNÍ A TUČNÝ FONT
                    pdfmetrics.registerFont(TTFont('CzechFont', font_path))
                    
                    # Pokud existuje bold verze, registruj i tu
                    bold_path = font_path.replace('.ttf', 'b.ttf').replace('.ttf', 'bd.ttf')
                    if os.path.exists(bold_path):
                        pdfmetrics.registerFont(TTFont('CzechFont-Bold', bold_path))
                    
                    print(f"[OK] Registrován český font: {font_path}")
                    font_registered = True
                    break
                except Exception as e:
                    print(f"[WARNING] Chyba při registraci fontu {font_path}: {e}")
                    continue
        
        # [OK] FALLBACK - DejaVu Sans má perfektní českou podporu
        if not font_registered:
            try:
                # Zkus stáhnout a použít DejaVu Sans (má skvělou českou podporu)
                import urllib.request
                import tempfile
                
                dejavu_url = "https://github.com/dejavu-fonts/dejavu-fonts/raw/master/ttf/DejaVuSans.ttf"
                temp_dir = tempfile.gettempdir()
                dejavu_path = os.path.join(temp_dir, "DejaVuSans.ttf")
                
                if not os.path.exists(dejavu_path):
                    urllib.request.urlretrieve(dejavu_url, dejavu_path)
                
                pdfmetrics.registerFont(TTFont('CzechFont', dejavu_path))
                font_registered = True
                print("[OK] Stažen a registrován DejaVu Sans font")
                
            except Exception as e:
                print(f"[WARNING] Nepodařilo se stáhnout DejaVu font: {e}")
        
        return font_registered
        
    except Exception as e:
        print(f"[ERROR] Chyba při registraci fontů: {e}")
        return False


# ============== HTML FAKTURA ==============

@print_bp.route("/<int:stredisko_id>/<int:rok>-<int:mesic>/faktura/html")
def vygenerovat_fakturu_html(stredisko_id, rok, mesic):
    """Generuje HTML fakturu"""
    data, error = get_faktura_data(stredisko_id, rok, mesic)
    if error:
        return error
    
    return render_template("print/faktura.html", **data)

# ============== PDF FAKTURA ==============

# V print.py - oprava pouze design části stávající funkce

# Odstraněno - _get_faktura_pdf_bytes() už se nepoužívá, nahrazeno WeasyPrint implementací



def _generate_simple_faktura_pdf(data):
    """Jednoduchá funkce pro generování PDF faktury podle HTML šablony"""
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    import io
    import os
    
    # Registrace českého fontu
    font_registered = False
    try:
        font_paths = [
            'C:/Windows/Fonts/arial.ttf',
            'C:/Windows/Fonts/calibri.ttf',
            '/System/Library/Fonts/Arial.ttf',
            '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
        ]
        
        for font_path in font_paths:
            if os.path.exists(font_path):
                try:
                    pdfmetrics.registerFont(TTFont('CzechFont', font_path))
                    font_registered = True
                    break
                except:
                    continue
    except:
        pass
    
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, 
                          rightMargin=20*mm, leftMargin=20*mm,
                          topMargin=20*mm, bottomMargin=20*mm)
    
    story = []
    styles = getSampleStyleSheet()
    
    # Nastav český font
    base_font = 'CzechFont' if font_registered else 'Helvetica'
    bold_font = 'CzechFont' if font_registered else 'Helvetica-Bold'
    
    if font_registered:
        styles['Normal'].fontName = base_font
        styles['Heading1'].fontName = bold_font
        styles['Heading2'].fontName = bold_font
        styles['Title'].fontName = bold_font
    
    # Vlastní styly podle HTML
    title_style = ParagraphStyle(
        'InvoiceTitle',
        parent=styles['Title'],
        fontSize=36,  # 2.5rem
        fontName=bold_font,
        textColor=colors.HexColor('#007bff'),  # Bootstrap primary blue
        spaceAfter=5,
        alignment=0  # Left align
    )
    
    subtitle_style = ParagraphStyle(
        'Subtitle',
        parent=styles['Normal'],
        fontSize=14,  # 1.2rem
        fontName=base_font,
        textColor=colors.HexColor('#6c757d'),  # Bootstrap muted
        spaceAfter=20
    )
    
    section_heading_style = ParagraphStyle(
        'SectionHeading',
        parent=styles['Heading2'],
        fontSize=14,
        fontName=bold_font,
        textColor=colors.HexColor('#007bff'),
        spaceAfter=12,
        spaceBefore=20
    )
    
    # Hlavička faktury s modrým ohraničením
    story.append(Paragraph("FAKTURA", title_style))
    story.append(Paragraph("DAŇOVÝ DOKLAD", subtitle_style))
    
    # Simulace modrého ohraničení pomocí tabulky
    divider_table = Table([['']],colWidths=[170*mm])
    divider_table.setStyle(TableStyle([
        ('LINEBELOW', (0, 0), (-1, -1), 3, colors.HexColor('#007bff')),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0)
    ]))
    story.append(divider_table)
    story.append(Spacer(1, 20))
    
    # Dodavatel a pravá strana s detaily faktury
    header_data = [
        [
            # Levý sloupec - Dodavatel (obyčejný text)
            [
                Paragraph(f"<b>{data['dodavatel'].nazev_sro if data['dodavatel'] else 'Your energy, s.r.o.'}</b>", styles['Normal']),
                Paragraph(f"{data['dodavatel'].adresa_radek_1 if data['dodavatel'] else 'Italská 2584/69'}", styles['Normal']),
                Paragraph(f"{data['dodavatel'].adresa_radek_2 if data['dodavatel'] else '120 00 Praha 2 - Vinohrady'}", styles['Normal']),
                Paragraph(f"<b>DIČ:</b> {data['dodavatel'].dic_sro if data['dodavatel'] else 'CZ24833851'}", styles['Normal']),
                Paragraph(f"<b>IČO:</b> {data['dodavatel'].ico_sro if data['dodavatel'] else '24833851'}", styles['Normal']),
                Spacer(1, 8),
                Paragraph(f"<b>Banka:</b> {data['dodavatel'].banka if data['dodavatel'] else 'Bankovní účet Raiffeisenbank a.s. CZK'}", styles['Normal']),
                Paragraph(f"<b>Č.úč.:</b> {data['dodavatel'].cislo_uctu if data['dodavatel'] else '5041011366/5500'}", styles['Normal']),
                Paragraph(f"<b>IBAN:</b> {data['dodavatel'].iban if data['dodavatel'] else 'CZ1055000000005041011366'}", styles['Normal']),
                Paragraph(f"<b>SWIFT/BIC:</b> {data['dodavatel'].swift if data['dodavatel'] else 'RZBCCZPP'}", styles['Normal'])
            ],
            # Pravý sloupec - šedý box s detaily faktury + bílý box s odběratelem
            [
                # Šedý box s detaily faktury (simulace pomocí tabulky)
                Table([
                    [Paragraph(f"<b>Faktura č. {data['faktura'].cislo_faktury if data['faktura'] else ''}</b>", styles['Heading3'])],
                    [Paragraph(f"<b>Konst. symbol:</b> {data['faktura'].konstantni_symbol if data['faktura'] else ''}", styles['Normal'])],
                    [Paragraph(f"<b>VS:</b> {data['faktura'].variabilni_symbol if data['faktura'] else ''}", styles['Normal'])]
                ], colWidths=[85*mm], style=TableStyle([
                    ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8f9fa')),
                    ('LEFTPADDING', (0, 0), (-1, -1), 12),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 12),
                    ('TOPPADDING', (0, 0), (-1, -1), 12),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
                    ('LINEABOVE', (0, 0), (-1, 0), 4, colors.HexColor('#007bff')),  # Modrý levý okraj
                    ('FONTNAME', (0, 0), (-1, -1), base_font)
                ])),
                
                Spacer(1, 15),
                
                # Bílý box s odběratelem
                Table([
                    [Paragraph('<font color="#007bff"><b>Odběratel:</b></font>', styles['Normal'])],
                    [Paragraph(f"<b>{data['odberatel'].nazev_sro if data['odberatel'] else ''}</b>", styles['Normal'])],
                    [Paragraph(f"{data['odberatel'].adresa_radek_1 if data['odberatel'] else ''}", styles['Normal'])],
                    [Paragraph(f"{data['odberatel'].adresa_radek_2 if data['odberatel'] else ''}", styles['Normal'])],
                    [Paragraph(f"<b>IČO:</b> {data['odberatel'].ico_sro if data['odberatel'] else ''}", styles['Normal'])],
                    [Paragraph(f"<b>DIČ:</b> {data['odberatel'].dic_sro if data['odberatel'] else ''}", styles['Normal'])]
                ], colWidths=[85*mm], style=TableStyle([
                    ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#dee2e6')),
                    ('BACKGROUND', (0, 0), (-1, -1), colors.white),
                    ('LEFTPADDING', (0, 0), (-1, -1), 15),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 15),
                    ('TOPPADDING', (0, 0), (-1, -1), 15),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 15),
                    ('FONTNAME', (0, 0), (-1, -1), base_font)
                ])),
                
                Spacer(1, 12),
                
                # Středisko info
                Paragraph(f"<b>Středisko:</b> {data['stredisko'].stredisko} {data['stredisko'].nazev_strediska}", styles['Normal']),
                Paragraph(f"{data['stredisko'].stredisko_mail if data['stredisko'].stredisko_mail else 'info@yourenergy.cz'}", styles['Normal'])
            ]
        ]
    ]
    
    header_table = Table(header_data, colWidths=[85*mm, 95*mm])
    header_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, 0), 'LEFT'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('FONTNAME', (0, 0), (-1, -1), base_font)
    ]))
    story.append(header_table)
    story.append(Spacer(1, 25))
    
    # Dodací a platební podmínky s modrým nadpisem
    story.append(Paragraph("Dodací a platební podmínky", section_heading_style))
    
    podminkz_data = [
        ['Datum vystavení:', data['faktura'].datum_vystaveni.strftime('%d.%m.%Y') if data['faktura'] and data['faktura'].datum_vystaveni else ''],
        ['Datum zdanitelného plnění:', data['faktura'].datum_zdanitelneho_plneni.strftime('%d.%m.%Y') if data['faktura'] and data['faktura'].datum_zdanitelneho_plneni else ''],
        ['Datum splatnosti:', data['faktura'].datum_splatnosti.strftime('%d.%m.%Y') if data['faktura'] and data['faktura'].datum_splatnosti else ''],
        ['Forma úhrady:', data['faktura'].forma_uhrady if data['faktura'] else 'Bezhotovostní platba'],
        ['Způsob dopravy:', 'Přenos po datové síti'],
        ['Místo plnění:', data['stredisko'].nazev_strediska if data['stredisko'] else '']
    ]
    
    podminky_table = Table(podminkz_data, colWidths=[60*mm, 120*mm])
    podminky_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), bold_font),
        ('FONTNAME', (1, 0), (1, -1), base_font),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0)
    ]))
    story.append(podminky_table)
    story.append(Spacer(1, 25))
    
    # Rekapitulace s modrým nadpisem  
    story.append(Paragraph("Rekapitulace", section_heading_style))
    
    # Tabulka rekapitulace s modrými hlavičkami podle HTML
    rekap_data = [['Rekapitulace', 'Základ daně', 'Sazba DPH', 'Částka DPH', 'Celkem vč. DPH']]
    
    # Přidej položky z rekapitulace
    for key, value in data['rekapitulace'].items():
        if value != 0:  # Pouze nenulové položky
            # Převeď klíče na čitelné názvy podle HTML
            nazvy_map = {
                'platba_za_jistic': 'Měsíční plat (za jistič)',
                'distribuce_vt': 'Plat za elektřinu ve VT', 
                'distribuce_nt': 'Plat za elektřinu ve NT',
                'systemove_sluzby': 'Cena za systémové služby',
                'poze': 'Podpora elektřiny z podporovaných zdrojů energie',
                'nesitova_infrastruktura': 'Poplatek za nesíťovou infrastrukturu',
                'dan_z_elektriny': 'Daň z elektřiny',
                'platba_za_elektrinu_vt': 'Plat za elektřinu ve VT',
                'platba_za_elektrinu_nt': 'Plat za elektřinu ve NT'
            }
            
            nazev = nazvy_map.get(key, key.replace('_', ' ').title())
            sazba_dph_procenta = int(data['sazba_dph'] * 100)
            dph_castka = value * data['sazba_dph']  # DPH část
            s_dph = value * (1 + data['sazba_dph'])  # S DPH
            
            rekap_data.append([
                nazev,
                f"{value:.2f}",
                f"{sazba_dph_procenta}",
                f"{dph_castka:.2f}", 
                f"{s_dph:.2f}"
            ])
    
    # Součtové řádky
    rekap_data.append(['', '', '', '', ''])  # Prázdný řádek  
    rekap_data.append(['CELKEM', f"{data['zaklad_bez_dph']:.2f}", '', f"{data['castka_dph']:.2f}", f"{data['celkem_vc_dph']:.2f}"])
    
    if data['zaloha_celkem_vc_dph'] > 0:
        rekap_data.append(['Uhrazené zálohy', '', '', '', f"-{data['zaloha_celkem_vc_dph']:.2f}"])
        rekap_data.append(['K PLATBĚ', '', '', '', f"{data['k_platbe']:.2f}"])
    
    rekap_table = Table(rekap_data, colWidths=[80*mm, 25*mm, 20*mm, 25*mm, 30*mm])
    rekap_table.setStyle(TableStyle([
        # Modrá hlavička podle HTML (#007bff)
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#007bff')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), bold_font),
        
        # Obsah tabulky
        ('FONTNAME', (0, 1), (-1, -1), base_font),
        ('FONTNAME', (0, -3), (-1, -1), bold_font),  # Poslední 3 řádky tučně
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        
        # Zvýrazni finální řádky
        ('BACKGROUND', (0, -2), (-1, -1), colors.HexColor('#007bff')),
        ('TEXTCOLOR', (0, -2), (-1, -1), colors.white),
        ('FONTSIZE', (0, -2), (-1, -1), 11)
    ]))
    story.append(rekap_table)
    story.append(Spacer(1, 20))
    
    # Poznámka na konci
    story.append(Paragraph("Rozpis jednotlivých položek faktury je uveden na následující straně.", styles['Normal']))
    story.append(Paragraph(f"<b>FAKTURA:</b> {data['faktura'].cislo_faktury if data['faktura'] else ''}", styles['Normal']))
    
    # Vytvoř PDF
    doc.build(story)
    pdf_data = buffer.getvalue()
    buffer.close()
    
    return pdf_data

def _generate_faktura_pdf_reportlab(data):
    """Fallback funkce pro generování PDF faktury pomocí ReportLab"""
    import io
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    
    print("[DEBUG] Začínám ReportLab fallback pro fakturu")
    
    # Vytvoř PDF dokument
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, 
                          rightMargin=20*mm, leftMargin=20*mm,
                          topMargin=20*mm, bottomMargin=20*mm)
    
    story = []
    styles = getSampleStyleSheet()
    
    # Nadpis
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        spaceAfter=30,
        alignment=1  # Center
    )
    story.append(Paragraph("FAKTURA", title_style))
    story.append(Spacer(1, 20))
    
    # Informace o faktuře
    if data['faktura']:
        story.append(Paragraph(f"<b>Číslo faktury:</b> {data['faktura'].cislo_faktury}", styles['Normal']))
        story.append(Paragraph(f"<b>Datum splatnosti:</b> {data['faktura'].datum_splatnosti}", styles['Normal']))
        story.append(Spacer(1, 20))
    
    # Informace o dodavateli a odběrateli
    if data['dodavatel']:
        story.append(Paragraph("<b>Dodavatel:</b>", styles['Heading2']))
        story.append(Paragraph(f"{data['dodavatel'].nazev_sro}", styles['Normal']))
        if data['dodavatel'].adresa_radek_1:
            story.append(Paragraph(f"{data['dodavatel'].adresa_radek_1}", styles['Normal']))
        if data['dodavatel'].adresa_radek_2:
            story.append(Paragraph(f"{data['dodavatel'].adresa_radek_2}", styles['Normal']))
        if data['dodavatel'].ico_sro:
            story.append(Paragraph(f"IČO: {data['dodavatel'].ico_sro}", styles['Normal']))
        story.append(Spacer(1, 15))
    
    if data['odberatel']:
        story.append(Paragraph("<b>Odběratel:</b>", styles['Heading2']))
        story.append(Paragraph(f"{data['odberatel'].nazev_sro}", styles['Normal']))
        if data['odberatel'].adresa_radek_1:
            story.append(Paragraph(f"{data['odberatel'].adresa_radek_1}", styles['Normal']))
        if data['odberatel'].adresa_radek_2:
            story.append(Paragraph(f"{data['odberatel'].adresa_radek_2}", styles['Normal']))
        if data['odberatel'].ico_sro:
            story.append(Paragraph(f"IČO: {data['odberatel'].ico_sro}", styles['Normal']))
        story.append(Spacer(1, 20))
    
    # Rekapitulace
    story.append(Paragraph("<b>Rekapitulace:</b>", styles['Heading2']))
    
    # Tabulka rekapitulace
    rekapitulace_data = [['Položka', 'Částka bez DPH']]
    
    for key, value in data['rekapitulace'].items():
        if value != 0:  # Zobraz pouze nenulové položky
            # Převeď klíč na čitelný název
            nazev = key.replace('_', ' ').title()
            rekapitulace_data.append([nazev, f"{value:.2f} Kč"])
    
    rekapitulace_data.append(['', ''])  # Prázdný řádek
    rekapitulace_data.append(['Základ bez DPH', f"{data['zaklad_bez_dph']:.2f} Kč"])
    rekapitulace_data.append(['DPH 21%', f"{data['castka_dph']:.2f} Kč"])
    rekapitulace_data.append(['CELKEM s DPH', f"{data['celkem_vc_dph']:.2f} Kč"])
    
    if data['zaloha_celkem_vc_dph'] > 0:
        rekapitulace_data.append(['Záloha', f"-{data['zaloha_celkem_vc_dph']:.2f} Kč"])
        rekapitulace_data.append(['K PLATBĚ', f"{data['k_platbe']:.2f} Kč"])
    
    table = Table(rekapitulace_data)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    story.append(table)
    
    # Vytvoř PDF
    doc.build(story)
    pdf_data = buffer.getvalue()
    buffer.close()
    
    print(f"[DEBUG] ReportLab PDF vygenerován, velikost: {len(pdf_data)} bytů")
    return pdf_data


@print_bp.route("/<int:stredisko_id>/<int:rok>-<int:mesic>/faktura/pdf")
def vygenerovat_fakturu_pdf(stredisko_id, rok, mesic):
    """Generuje PDF fakturu z HTML šablony pomocí WeasyPrint"""
    if not session.get("user_id"):
        return redirect("/login")

    stredisko = Stredisko.query.get_or_404(stredisko_id)
    if stredisko.user_id != session["user_id"]:
        return "Nepovolený přístup", 403

    try:
        # Načti data stejně jako v HTML verzi
        data, error = get_faktura_data(stredisko_id, rok, mesic)
        if error:
            raise Exception(f"Chyba při načítání dat: {error}")

        # Vybraz šablonu na základě fakturovat_jen_distribuci
        if data['faktura'] and data['faktura'].fakturovat_jen_distribuci:
            template_name = "print/faktura_jen_distribuce.html"
        else:
            template_name = "print/faktura.html"

        # Vygeneruj HTML pomocí příslušné šablony
        html_content = render_template(template_name, **data)

        # Převeď HTML na PDF pomocí WeasyPrint
        pdf_bytes = _safe_weasyprint_convert(html_content)

        if isinstance(pdf_bytes, str):
            # Pokud WeasyPrint selhal, vrať chybovou zprávu
            return make_response(pdf_bytes, 500, {'Content-Type': 'text/html; charset=utf-8'})

        # Vytvoř odpověď s PDF
        response = make_response(pdf_bytes)
        response.headers['Content-Type'] = 'application/pdf'
        # Název souboru podle čísla faktury
        cislo_faktury = data['faktura'].cislo_faktury if data['faktura'] and data['faktura'].cislo_faktury else f'{stredisko_id}_{rok}_{mesic:02d}'
        response.headers['Content-Disposition'] = f'inline; filename=faktura_{cislo_faktury}.pdf'
        return response

    except Exception as e:
        return f"Chyba při generování PDF faktury: {str(e)}", 500


@print_bp.route("/<int:stredisko_id>/<int:rok>-<int:mesic>/zalohova/html")
def vygenerovat_zalohu_html(stredisko_id, rok, mesic):
    """Generuje HTML zálohovou fakturu"""
    if not session.get("user_id"):
        return redirect("/login")

    stredisko = Stredisko.query.get_or_404(stredisko_id)
    if stredisko.user_id != session["user_id"]:
        return "Nepovolený přístup", 403

    # Najdi období
    obdobi = ObdobiFakturace.query.filter_by(
        stredisko_id=stredisko_id, rok=rok, mesic=mesic
    ).first_or_404()

    # Načti všechna potřebná data
    zaloha = ZalohovaFaktura.query.filter_by(stredisko_id=stredisko_id, obdobi_id=obdobi.id).first()
    dodavatel = InfoDodavatele.query.filter_by(stredisko_id=stredisko_id).first()
    odberatel = InfoOdberatele.query.filter_by(stredisko_id=stredisko_id).first()
    vystavovatel = InfoVystavovatele.query.filter_by(stredisko_id=stredisko_id).first()

    return render_template("print/zalohova_faktura.html", 
                          stredisko=stredisko,
                          obdobi=obdobi,
                          zaloha=zaloha,
                          dodavatel=dodavatel,
                          odberatel=odberatel,
                          vystavovatel=vystavovatel)


@print_bp.route("/<int:stredisko_id>/<int:rok>-<int:mesic>/zalohova/pdf")
def vygenerovat_zalohu_pdf(stredisko_id, rok, mesic):
    """Generuje PDF zálohovou fakturu pomocí WeasyPrint"""
    if not session.get("user_id"):
        return redirect("/login")

    stredisko = Stredisko.query.get_or_404(stredisko_id)
    if stredisko.user_id != session["user_id"]:
        return "Nepovolený přístup", 403

    try:
        # Najdi období
        obdobi = ObdobiFakturace.query.filter_by(
            stredisko_id=stredisko_id, rok=rok, mesic=mesic
        ).first_or_404()

        # Načti všechna potřebná data (stejná logika jako HTML verze)
        zaloha = ZalohovaFaktura.query.filter_by(stredisko_id=stredisko_id, obdobi_id=obdobi.id).first()
        dodavatel = InfoDodavatele.query.filter_by(stredisko_id=stredisko_id).first()
        odberatel = InfoOdberatele.query.filter_by(stredisko_id=stredisko_id).first()
        vystavovatel = InfoVystavovatele.query.filter_by(stredisko_id=stredisko_id).first()

        # Vygeneruj HTML pomocí stejné šablony jako HTML verze
        html_content = render_template("print/zalohova_faktura.html",
                          stredisko=stredisko,
                          obdobi=obdobi,
                          zaloha=zaloha,
                          dodavatel=dodavatel,
                          odberatel=odberatel,
                          vystavovatel=vystavovatel)

        # Převeď HTML na PDF pomocí WeasyPrint
        pdf_bytes = _safe_weasyprint_convert(html_content)

        if isinstance(pdf_bytes, str):
            # Pokud WeasyPrint selhal, vrať chybovou zprávu
            return make_response(pdf_bytes, 500, {'Content-Type': 'text/html; charset=utf-8'})

        # Vytvoř odpověď s PDF
        response = make_response(pdf_bytes)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'inline; filename=zalohova_{rok}_{mesic:02d}.pdf'

        return response

    except Exception as e:
        flash(f"Chyba při generování PDF zálohové faktury: {str(e)}")
        return redirect(url_for('fakturace.fakturace', stredisko_id=stredisko_id, obdobi_id=obdobi.id))

# Nahraď existující route v print.py:

@print_bp.route("/<int:stredisko_id>/<int:rok>-<int:mesic>/priloha1/html")
def vygenerovat_prilohu1_html(stredisko_id, rok, mesic):
    """Generuje HTML přílohu 1 - hodnoty měření"""
    if not session.get("user_id"):
        return redirect("/login")

    stredisko = Stredisko.query.get_or_404(stredisko_id)
    if stredisko.user_id != session["user_id"]:
        return "Nepovolený přístup", 403

    # Najdi období
    obdobi = ObdobiFakturace.query.filter_by(
        stredisko_id=stredisko_id, rok=rok, mesic=mesic
    ).first_or_404()

    # Načti všechna potřebná data
    faktura = Faktura.query.filter_by(stredisko_id=stredisko_id, obdobi_id=obdobi.id).first()
    dodavatel = InfoDodavatele.query.filter_by(stredisko_id=stredisko_id).first()
    
    # Načti odečty pro dané období
    odecty_raw = Odecet.query\
        .filter_by(stredisko_id=stredisko_id, obdobi_id=obdobi.id)\
        .order_by(Odecet.oznaceni)\
        .all()
    
    # Načti odběrná místa pro středisko
    odberna_mista = {om.cislo_om: om for om in OdberneMisto.query.filter_by(stredisko_id=stredisko_id).all()}
    
    # Spáruj odečty s odběrnými místy
    odecty = []
    for odecet in odecty_raw:
        # Zkus najít odpovídající odběrné místo
        om = None
        if odecet.oznaceni in odberna_mista:
            om = odberna_mista[odecet.oznaceni]
        else:
            # Zkus s doplněnými nulami
            oznaceni_padded = odecet.oznaceni.zfill(7) if odecet.oznaceni else ""
            if oznaceni_padded in odberna_mista:
                om = odberna_mista[oznaceni_padded]
            else:
                # Zkus bez vedoucích nul
                oznaceni_stripped = odecet.oznaceni.lstrip('0') if odecet.oznaceni else ""
                if oznaceni_stripped in odberna_mista:
                    om = odberna_mista[oznaceni_stripped]
        
        if om:  # Pouze pokud najdeme odpovídající odběrné místo
            odecty.append((odecet, om))
    
    # Převeď na formát pro template - přidej odkaz na OM
    odecty_data = []
    for odecet, om in odecty:
        # Přidej odkaz na odběrné místo do objektu odečtu
        odecet.odberne_misto = om
        odecty_data.append(odecet)

    return render_template("print/priloha1.html", 
                        stredisko=stredisko,
                        obdobi=obdobi,
                        faktura=faktura,
                        dodavatel=dodavatel,
                        odecty=odecty_data)

# V print.py - oprava PDF přílohy 1 podle vzoru


@print_bp.route("/<int:stredisko_id>/<int:rok>-<int:mesic>/priloha1/pdf")
def vygenerovat_prilohu1_pdf(stredisko_id, rok, mesic):
    """Generuje PDF přílohu 1 - hodnoty měření pomocí WeasyPrint"""
    if not session.get("user_id"):
        return redirect("/login")

    stredisko = Stredisko.query.get_or_404(stredisko_id)
    if stredisko.user_id != session["user_id"]:
        return "Nepovolený přístup", 403

    try:
        # Najdi období
        obdobi = ObdobiFakturace.query.filter_by(
            stredisko_id=stredisko_id, rok=rok, mesic=mesic
        ).first_or_404()

        # Načti všechna potřebná data (stejná logika jako HTML verze)
        faktura = Faktura.query.filter_by(stredisko_id=stredisko_id, obdobi_id=obdobi.id).first()
        dodavatel = InfoDodavatele.query.filter_by(stredisko_id=stredisko_id).first()

        # Načti odečty pro dané období
        odecty_raw = Odecet.query\
            .filter_by(stredisko_id=stredisko_id, obdobi_id=obdobi.id)\
            .order_by(Odecet.oznaceni)\
            .all()

        # Načti odběrná místa pro středisko
        odberna_mista = {om.cislo_om: om for om in OdberneMisto.query.filter_by(stredisko_id=stredisko_id).all()}

        # Spáruj odečty s odběrnými místy
        odecty = []
        for odecet in odecty_raw:
            # Zkus najít odpovídající odběrné místo
            om = None
            if odecet.oznaceni in odberna_mista:
                om = odberna_mista[odecet.oznaceni]
            else:
                # Zkus s doplněnými nulami
                oznaceni_padded = odecet.oznaceni.zfill(7) if odecet.oznaceni else ""
                if oznaceni_padded in odberna_mista:
                    om = odberna_mista[oznaceni_padded]
                else:
                    # Zkus bez vedoucích nul
                    oznaceni_stripped = odecet.oznaceni.lstrip('0') if odecet.oznaceni else ""
                    if oznaceni_stripped in odberna_mista:
                        om = odberna_mista[oznaceni_stripped]

            if om:  # Pouze pokud najdeme odpovídající odběrné místo
                odecty.append((odecet, om))

        # Převeď na formát pro template - přidej odkaz na OM
        odecty_data = []
        for odecet, om in odecty:
            # Přidej odkaz na odběrné místo do objektu odečtu
            odecet.odberne_misto = om
            odecty_data.append(odecet)

        # Vygeneruj HTML pomocí stejné šablony jako HTML verze
        html_content = render_template("print/priloha1.html",
                            stredisko=stredisko,
                            obdobi=obdobi,
                            faktura=faktura,
                            dodavatel=dodavatel,
                            odecty=odecty_data)

        # Převeď HTML na PDF pomocí WeasyPrint
        pdf_bytes = _safe_weasyprint_convert(html_content)

        if isinstance(pdf_bytes, str):
            # Pokud WeasyPrint selhal, vrať chybovou zprávu
            return make_response(pdf_bytes, 500, {'Content-Type': 'text/html; charset=utf-8'})

        # Vytvoř odpověď s PDF
        response = make_response(pdf_bytes)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'inline; filename=priloha1_{rok}_{mesic:02d}.pdf'

        return response

    except Exception as e:
        flash(f"Chyba při generování PDF přílohy 1: {str(e)}")
        return redirect(url_for('fakturace.fakturace', stredisko_id=stredisko_id, obdobi_id=obdobi.id))

# ODSTRANĚNO - Používáme pouze WeasyPrint a HTML šablony

@print_bp.route("/<int:stredisko_id>/<int:rok>-<int:mesic>/priloha2/html")
def vygenerovat_prilohu2_html(stredisko_id, rok, mesic):
    """Generuje HTML přílohu 2 - rozpis položek za odběrná místa"""
    if not session.get("user_id"):
        return redirect("/login")

    stredisko = Stredisko.query.get_or_404(stredisko_id)
    if stredisko.user_id != session["user_id"]:
        return "Nepovolený přístup", 403

    # Najdi období
    obdobi = ObdobiFakturace.query.filter_by(
        stredisko_id=stredisko_id, rok=rok, mesic=mesic
    ).first_or_404()

    # Načti základní data
    faktura = Faktura.query.filter_by(stredisko_id=stredisko_id, obdobi_id=obdobi.id).first()
    dodavatel = InfoDodavatele.query.filter_by(stredisko_id=stredisko_id).first()
    
    # Načti všechny výpočty s odběrnými místy pro dané období
    vypocty_om = db.session.query(VypocetOM, OdberneMisto)\
        .join(OdberneMisto, VypocetOM.odberne_misto_id == OdberneMisto.id)\
        .filter(VypocetOM.obdobi_id == obdobi.id)\
        .filter(OdberneMisto.stredisko_id == stredisko_id)\
        .order_by(OdberneMisto.cislo_om)\
        .all()
    
    if not vypocty_om:
        return "Nejsou k dispozici výpočty pro vybrané období.", 400

    # Připrav data pro template
    vypocty_data = []
    sazba_dph = float(faktura.sazba_dph / 100) if faktura and faktura.sazba_dph else 0.21
    
    for vypocet, om in vypocty_om:
        # Vypočítej minimum z POZE - převeď na float
        poze_minimum = min(float(vypocet.poze_dle_jistice or 0), float(vypocet.poze_dle_spotreby or 0))
        
        # Zjisti zda fakturovat jen distribuci
        fakturovat_jen_distribuci = faktura.fakturovat_jen_distribuci if faktura else False

        # Celková suma za OM - použij předpočítané hodnoty bez distribuce pokud jsou k dispozici
        if not fakturovat_jen_distribuci and hasattr(vypocet, 'celkem_vc_dph_bez_di') and vypocet.celkem_vc_dph_bez_di:
            celkem_om = float(vypocet.celkem_vc_dph_bez_di or 0) / (1 + sazba_dph)  # Převeď zpět na základ bez DPH
        else:
            # Standardní výpočet - převeď všechny hodnoty na float
            celkem_om = (
                float(vypocet.mesicni_plat or 0) +
                float(vypocet.platba_za_elektrinu_vt or 0) +
                float(vypocet.platba_za_elektrinu_nt or 0) +
                (float(vypocet.platba_za_jistic or 0) if not fakturovat_jen_distribuci else 0) +
                (float(vypocet.platba_za_distribuci_vt or 0) if not fakturovat_jen_distribuci else 0) +
                (float(vypocet.platba_za_distribuci_nt or 0) if not fakturovat_jen_distribuci else 0) +
                float(vypocet.systemove_sluzby or 0) +
                poze_minimum +
                float(vypocet.nesitova_infrastruktura or 0) +
                float(vypocet.dan_z_elektriny or 0)
            )
        
        # Načti odečet pro získání spotřeb
        odecet = Odecet.query.filter_by(
            stredisko_id=stredisko_id,
            obdobi_id=obdobi.id,
            oznaceni=om.cislo_om.zfill(7) if om.cislo_om else None
        ).first()
        
        # Výpočet jednotkových cen
        # Spotřeby v MWh
        spotreba_vt_mwh = float(odecet.spotreba_vt or 0) / 1000 if odecet else 0
        spotreba_nt_mwh = float(odecet.spotreba_nt or 0) / 1000 if odecet else 0
        celkova_spotreba_mwh = spotreba_vt_mwh + spotreba_nt_mwh
        
        # Jednotkové ceny (cena / spotřeba)
        jednotkova_cena_elektriny_vt = float(vypocet.platba_za_elektrinu_vt or 0) / spotreba_vt_mwh if spotreba_vt_mwh > 0 else 0
        jednotkova_cena_elektriny_nt = float(vypocet.platba_za_elektrinu_nt or 0) / spotreba_nt_mwh if spotreba_nt_mwh > 0 else 0
        jednotkova_cena_distribuce_vt = float(vypocet.platba_za_distribuci_vt or 0) / spotreba_vt_mwh if spotreba_vt_mwh > 0 else 0
        jednotkova_cena_distribuce_nt = float(vypocet.platba_za_distribuci_nt or 0) / spotreba_nt_mwh if spotreba_nt_mwh > 0 else 0
        jednotkova_cena_systemove_sluzby = float(vypocet.systemove_sluzby or 0) / celkova_spotreba_mwh if celkova_spotreba_mwh > 0 else 0
        jednotkova_cena_poze = float(poze_minimum) / celkova_spotreba_mwh if celkova_spotreba_mwh > 0 else 0
        jednotkova_cena_dan = float(vypocet.dan_z_elektriny or 0) / celkova_spotreba_mwh if celkova_spotreba_mwh > 0 else 0

        vypocty_data.append({
            'om': om,
            'vypocet': vypocet,
            'odecet': odecet,
            'poze_minimum': poze_minimum,
            'celkem_om': celkem_om,
            'sazba_dph': sazba_dph,
            # Spotřeby v MWh
            'spotreba_vt_mwh': spotreba_vt_mwh,
            'spotreba_nt_mwh': spotreba_nt_mwh,
            'celkova_spotreba_mwh': celkova_spotreba_mwh,
            # Jednotkové ceny
            'jednotkova_cena_elektriny_vt': jednotkova_cena_elektriny_vt,
            'jednotkova_cena_elektriny_nt': jednotkova_cena_elektriny_nt,
            'jednotkova_cena_distribuce_vt': jednotkova_cena_distribuce_vt,
            'jednotkova_cena_distribuce_nt': jednotkova_cena_distribuce_nt,
            'jednotkova_cena_systemove_sluzby': jednotkova_cena_systemove_sluzby,
            'jednotkova_cena_poze': jednotkova_cena_poze,
            'jednotkova_cena_dan': jednotkova_cena_dan
        })

    # [OK] OPRAVA: Renderuj template s UTF-8 kódováním
    try:
        # Vybraz šablonu na základě fakturovat_jen_distribuci
        if faktura and faktura.fakturovat_jen_distribuci:
            template_name = "print/priloha2_jen_distribuce.html"
        else:
            template_name = "print/priloha2.html"

        html_content = render_template(template_name,
                            stredisko=stredisko,
                            obdobi=obdobi,
                            faktura=faktura,
                            dodavatel=dodavatel,
                            vypocty_data=vypocty_data)
        
        # Vytvoř response s explicitním UTF-8 kódováním
        response = make_response(html_content.encode('utf-8'))
        response.headers['Content-Type'] = 'text/html; charset=utf-8'
        
        return response
        
    except UnicodeEncodeError as e:
        # Fallback pro problematické znaky
        print(f"Unicode error: {e}")
        # Vybraz šablonu na základě fakturovat_jen_distribuci
        if faktura and faktura.fakturovat_jen_distribuci:
            template_name = "print/priloha2_jen_distribuce.html"
        else:
            template_name = "print/priloha2.html"

        html_content = render_template(template_name,
                            stredisko=stredisko,
                            obdobi=obdobi,
                            faktura=faktura,
                            dodavatel=dodavatel,
                            vypocty_data=vypocty_data)
        
        response = make_response(html_content)
        response.headers['Content-Type'] = 'text/html; charset=utf-8'
        
        return response

# ==== POUZE WEASYPRINT A HTML ŠABLONY ====

@print_bp.route("/<int:stredisko_id>/<int:rok>-<int:mesic>/priloha2/pdf")
def priloha2_pdf_nova(stredisko_id, rok, mesic):
    """Generování PDF přílohy 2 s daty z databáze pomocí WeasyPrint"""
    if not session.get("user_id"):
        return redirect("/login")

    try:
        stredisko = Stredisko.query.get_or_404(stredisko_id)
        if stredisko.user_id != session["user_id"]:
            return "Nepovolený přístup", 403

        # Najdi období
        obdobi = ObdobiFakturace.query.filter_by(
            stredisko_id=stredisko_id, rok=rok, mesic=mesic
        ).first_or_404()

        # Načti základní data
        faktura = Faktura.query.filter_by(stredisko_id=stredisko_id, obdobi_id=obdobi.id).first()
        dodavatel = InfoDodavatele.query.filter_by(stredisko_id=stredisko_id).first()

        # Načti všechny výpočty s odběrnými místy pro dané období - STEJNÝ QUERY JAKO HTML
        vypocty_om = db.session.query(VypocetOM, OdberneMisto)\
            .join(OdberneMisto, VypocetOM.odberne_misto_id == OdberneMisto.id)\
            .filter(VypocetOM.obdobi_id == obdobi.id)\
            .filter(OdberneMisto.stredisko_id == stredisko_id)\
            .order_by(OdberneMisto.cislo_om)\
            .all()

        if not vypocty_om:
            return "Nejsou k dispozici výpočty pro vybrané období.", 400

        # Připrav data pro template - STEJNÁ LOGIKA JAKO HTML
        vypocty_data = []
        sazba_dph = float(faktura.sazba_dph / 100) if faktura and faktura.sazba_dph else 0.21

        for vypocet, om in vypocty_om:
            # Vypočítej minimum z POZE - převeď na float - STEJNÝ VÝPOČET JAKO HTML
            poze_minimum = min(float(vypocet.poze_dle_jistice or 0), float(vypocet.poze_dle_spotreby or 0))

            # Zjisti zda fakturovat jen distribuci (tam kde ještě není)
            if 'fakturovat_jen_distribuci' not in locals():
                fakturovat_jen_distribuci = faktura.fakturovat_jen_distribuci if faktura else False

            # Celková suma za OM - použij předpočítané hodnoty jen distribuce pokud jsou k dispozici
            if fakturovat_jen_distribuci and hasattr(vypocet, 'celkem_vc_dph_bez_di') and vypocet.celkem_vc_dph_bez_di:
                celkem_om = float(vypocet.celkem_vc_dph_bez_di or 0) / (1 + sazba_dph)  # Převeď zpět na základ bez DPH
            else:
                # Standardní výpočet (kompletní faktura) - převeď všechny hodnoty na float
                celkem_om = (
                    float(vypocet.mesicni_plat or 0) +
                    float(vypocet.platba_za_elektrinu_vt or 0) +
                    float(vypocet.platba_za_elektrinu_nt or 0) +
                    float(vypocet.platba_za_jistic or 0) +
                    float(vypocet.platba_za_distribuci_vt or 0) +
                    float(vypocet.platba_za_distribuci_nt or 0) +
                    float(vypocet.systemove_sluzby or 0) +
                    poze_minimum +
                    float(vypocet.nesitova_infrastruktura or 0) +
                    float(vypocet.dan_z_elektriny or 0)
                )

            # Načti odečet pro získání spotřeb - STEJNÝ ZPŮSOB JAKO HTML
            odecet = Odecet.query.filter_by(
                stredisko_id=stredisko_id,
                obdobi_id=obdobi.id,
                oznaceni=om.cislo_om.zfill(7) if om.cislo_om else None
            ).first()

            # Výpočet jednotkových cen - STEJNÁ LOGIKA JAKO HTML
            # Spotřeby v MWh
            spotreba_vt_mwh = float(odecet.spotreba_vt or 0) / 1000 if odecet else 0
            spotreba_nt_mwh = float(odecet.spotreba_nt or 0) / 1000 if odecet else 0
            celkova_spotreba_mwh = spotreba_vt_mwh + spotreba_nt_mwh

            # Jednotkové ceny (cena / spotřeba) - STEJNÝ VÝPOČET JAKO HTML
            jednotkova_cena_elektriny_vt = float(vypocet.platba_za_elektrinu_vt or 0) / spotreba_vt_mwh if spotreba_vt_mwh > 0 else 0
            jednotkova_cena_elektriny_nt = float(vypocet.platba_za_elektrinu_nt or 0) / spotreba_nt_mwh if spotreba_nt_mwh > 0 else 0
            jednotkova_cena_distribuce_vt = float(vypocet.platba_za_distribuci_vt or 0) / spotreba_vt_mwh if spotreba_vt_mwh > 0 else 0
            jednotkova_cena_distribuce_nt = float(vypocet.platba_za_distribuci_nt or 0) / spotreba_nt_mwh if spotreba_nt_mwh > 0 else 0
            jednotkova_cena_systemove_sluzby = float(vypocet.systemove_sluzby or 0) / celkova_spotreba_mwh if celkova_spotreba_mwh > 0 else 0
            jednotkova_cena_poze = float(poze_minimum) / celkova_spotreba_mwh if celkova_spotreba_mwh > 0 else 0
            jednotkova_cena_dan = float(vypocet.dan_z_elektriny or 0) / celkova_spotreba_mwh if celkova_spotreba_mwh > 0 else 0

            vypocty_data.append({
                'om': om,
                'vypocet': vypocet,
                'odecet': odecet,
                'poze_minimum': poze_minimum,
                'celkem_om': celkem_om,
                'sazba_dph': sazba_dph,
                # Spotřeby v MWh
                'spotreba_vt_mwh': spotreba_vt_mwh,
                'spotreba_nt_mwh': spotreba_nt_mwh,
                'celkova_spotreba_mwh': celkova_spotreba_mwh,
                # Jednotkové ceny
                'jednotkova_cena_elektriny_vt': jednotkova_cena_elektriny_vt,
                'jednotkova_cena_elektriny_nt': jednotkova_cena_elektriny_nt,
                'jednotkova_cena_distribuce_vt': jednotkova_cena_distribuce_vt,
                'jednotkova_cena_distribuce_nt': jednotkova_cena_distribuce_nt,
                'jednotkova_cena_systemove_sluzby': jednotkova_cena_systemove_sluzby,
                'jednotkova_cena_poze': jednotkova_cena_poze,
                'jednotkova_cena_dan': jednotkova_cena_dan
            })

        # Vybraz šablonu na základě fakturovat_jen_distribuci
        if faktura and faktura.fakturovat_jen_distribuci:
            template_name = "print/priloha2_jen_distribuce.html"
        else:
            template_name = "print/priloha2.html"

        # Vygeneruj HTML pomocí příslušné šablony
        html_content = render_template(template_name,
                                     stredisko=stredisko,
                                     obdobi=obdobi,
                                     faktura=faktura,
                                     dodavatel=dodavatel,
                                     vypocty_data=vypocty_data)

        # Převeď HTML na PDF pomocí WeasyPrint
        if WEASYPRINT_AVAILABLE:
            try:
                pdf_bytes = _safe_weasyprint_convert(html_content)
                response = make_response(pdf_bytes)
                response.headers['Content-Type'] = 'application/pdf'
                response.headers['Content-Disposition'] = f'inline; filename=priloha2_{rok}_{mesic:02d}.pdf'
                return response
            except Exception as weasy_error:
                raise Exception(f"WeasyPrint error in priloha2: {weasy_error}")
        else:
            raise Exception("WeasyPrint není dostupný pro přílohu 2")

    except Exception as e:
        return f"Chyba při generování PDF přílohy 2: {str(e)}", 500

# Zbytek funkcí je nyní čistý - používá jen WeasyPrint a HTML šablony

@print_bp.route("/<int:stredisko_id>/<int:rok>-<int:mesic>/priloha2/test")
def test_priloha2_route(stredisko_id, rok, mesic):
    """ÚPLNĚ JEDNODUCHÝ TEST - bez databáze"""
    return f"TEST ROUTE WORKS: stredisko={stredisko_id}, rok={rok}, mesic={mesic}"

# Další route functions následují...

# ==== KOMPLETNÍ PDF - POUZE WEASYPRINT ====

@print_bp.route("/<int:stredisko_id>/<int:rok>-<int:mesic>/kompletni/pdf")
def vygenerovat_kompletni_pdf(stredisko_id, rok, mesic):
    """Generuje kompletní PDF - faktura + příloha 1 + příloha 2 v jednom souboru pomocí HTML šablon"""
    if not session.get("user_id"):
        return redirect("/login")

    stredisko = Stredisko.query.get_or_404(stredisko_id)
    if stredisko.user_id != session["user_id"]:
        return "Nepovolený přístup", 403

    try:
        print("[INFO] Generuji kompletní PDF kombinací HTML šablon...")

        if not WEASYPRINT_AVAILABLE:
            raise Exception("WeasyPrint není dostupný - nelze generovat kompletní PDF")

        # Načti data pro HTML šablony (stejná data jako jednotlivé route)
        data, error = get_faktura_data(stredisko_id, rok, mesic)
        if error:
            raise Exception(f"Chyba při načítání dat: {error}")

        # 1. HTML FAKTURA (používá faktura.html nebo faktura_jen_distribuce.html)
        print("[INFO] Generuji HTML fakturu...")
        if data['faktura'] and data['faktura'].fakturovat_jen_distribuci:
            faktura_template = "print/faktura_jen_distribuce.html"
        else:
            faktura_template = "print/faktura.html"
        faktura_html = render_template(faktura_template, **data)

        # 2. HTML PŘÍLOHA 1 (používá priloha1.html - stejná data jako route)
        print("[INFO] Generuji HTML přílohu 1...")
        # Připrav data pro přílohu 1 stejně jako v route vygenerovat_prilohu1_html
        stredisko_obj = data['stredisko']
        obdobi = data['obdobi']
        faktura = data['faktura']
        dodavatel = data['dodavatel']

        # Načti odečty stejně jako v originální route
        odecty_raw = Odečet.query\
            .filter_by(stredisko_id=stredisko_id, obdobi_id=obdobi.id)\
            .order_by(Odečet.oznaceni)\
            .all()

        odberna_mista = {om.cislo_om: om for om in OdberneMisto.query.filter_by(stredisko_id=stredisko_id).all()}

        odecty_data = []
        for odecet in odecty_raw:
            om = None
            if odecet.oznaceni in odberna_mista:
                om = odberna_mista[odecet.oznaceni]
            else:
                oznaceni_padded = odecet.oznaceni.zfill(7) if odecet.oznaceni else ""
                if oznaceni_padded in odberna_mista:
                    om = odberna_mista[oznaceni_padded]
                else:
                    oznaceni_stripped = odecet.oznaceni.lstrip('0') if odecet.oznaceni else ""
                    if oznaceni_stripped in odberna_mista:
                        om = odberna_mista[oznaceni_stripped]

            if om:
                # Přidej odběrné místo jako atribut k odečtu (ne jako slovník!)
                setattr(odecet, 'odberne_misto', om)
                odecty_data.append(odecet)

        priloha1_html = render_template("print/priloha1.html",
                                       stredisko=stredisko_obj,
                                       obdobi=obdobi,
                                       faktura=faktura,
                                       dodavatel=dodavatel,
                                       odecty=odecty_data)

        # 3. HTML PŘÍLOHA 2 (používá priloha2.html - stejná data jako route)
        print("[INFO] Generuji HTML přílohu 2...")
        # Připrav data pro přílohu 2 STEJNĚ jako v HTML route vygenerovat_prilohu2_html
        vypocty_om = db.session.query(VypocetOM, OdberneMisto)\
            .join(OdberneMisto, VypocetOM.odberne_misto_id == OdberneMisto.id)\
            .filter(VypocetOM.obdobi_id == obdobi.id)\
            .filter(OdberneMisto.stredisko_id == stredisko_id)\
            .order_by(OdberneMisto.cislo_om)\
            .all()

        # Připrav data pro template - STEJNÁ LOGIKA JAKO HTML
        vypocty_data = []
        sazba_dph = float(faktura.sazba_dph / 100) if faktura and faktura.sazba_dph else 0.21

        for vypocet, om in vypocty_om:
            # Vypočítej minimum z POZE - převeď na float - STEJNÝ VÝPOČET JAKO HTML
            poze_minimum = min(float(vypocet.poze_dle_jistice or 0), float(vypocet.poze_dle_spotreby or 0))

            # Zjisti zda fakturovat jen distribuci (tam kde ještě není)
            if 'fakturovat_jen_distribuci' not in locals():
                fakturovat_jen_distribuci = faktura.fakturovat_jen_distribuci if faktura else False

            # Celková suma za OM - použij předpočítané hodnoty jen distribuce pokud jsou k dispozici
            if fakturovat_jen_distribuci and hasattr(vypocet, 'celkem_vc_dph_bez_di') and vypocet.celkem_vc_dph_bez_di:
                celkem_om = float(vypocet.celkem_vc_dph_bez_di or 0) / (1 + sazba_dph)  # Převeď zpět na základ bez DPH
            else:
                # Standardní výpočet (kompletní faktura) - převeď všechny hodnoty na float
                celkem_om = (
                    float(vypocet.mesicni_plat or 0) +
                    float(vypocet.platba_za_elektrinu_vt or 0) +
                    float(vypocet.platba_za_elektrinu_nt or 0) +
                    float(vypocet.platba_za_jistic or 0) +
                    float(vypocet.platba_za_distribuci_vt or 0) +
                    float(vypocet.platba_za_distribuci_nt or 0) +
                    float(vypocet.systemove_sluzby or 0) +
                    poze_minimum +
                    float(vypocet.nesitova_infrastruktura or 0) +
                    float(vypocet.dan_z_elektriny or 0)
                )

            # Načti odečet pro získání spotřeb - STEJNÝ ZPŮSOB JAKO HTML
            odecet = Odecet.query.filter_by(
                stredisko_id=stredisko_id,
                obdobi_id=obdobi.id,
                oznaceni=om.cislo_om.zfill(7) if om.cislo_om else None
            ).first()

            # Výpočet jednotkových cen - STEJNÁ LOGIKA JAKO HTML
            # Spotřeby v MWh
            spotreba_vt_mwh = float(odecet.spotreba_vt or 0) / 1000 if odecet else 0
            spotreba_nt_mwh = float(odecet.spotreba_nt or 0) / 1000 if odecet else 0
            celkova_spotreba_mwh = spotreba_vt_mwh + spotreba_nt_mwh

            # Jednotkové ceny (cena / spotřeba) - STEJNÝ VÝPOČET JAKO HTML
            jednotkova_cena_elektriny_vt = float(vypocet.platba_za_elektrinu_vt or 0) / spotreba_vt_mwh if spotreba_vt_mwh > 0 else 0
            jednotkova_cena_elektriny_nt = float(vypocet.platba_za_elektrinu_nt or 0) / spotreba_nt_mwh if spotreba_nt_mwh > 0 else 0
            jednotkova_cena_distribuce_vt = float(vypocet.platba_za_distribuci_vt or 0) / spotreba_vt_mwh if spotreba_vt_mwh > 0 else 0
            jednotkova_cena_distribuce_nt = float(vypocet.platba_za_distribuci_nt or 0) / spotreba_nt_mwh if spotreba_nt_mwh > 0 else 0
            jednotkova_cena_systemove_sluzby = float(vypocet.systemove_sluzby or 0) / celkova_spotreba_mwh if celkova_spotreba_mwh > 0 else 0
            jednotkova_cena_poze = float(poze_minimum) / celkova_spotreba_mwh if celkova_spotreba_mwh > 0 else 0
            jednotkova_cena_dan = float(vypocet.dan_z_elektriny or 0) / celkova_spotreba_mwh if celkova_spotreba_mwh > 0 else 0

            vypocty_data.append({
                'om': om,
                'vypocet': vypocet,
                'odecet': odecet,
                'poze_minimum': poze_minimum,
                'celkem_om': celkem_om,
                'sazba_dph': sazba_dph,
                # Spotřeby v MWh
                'spotreba_vt_mwh': spotreba_vt_mwh,
                'spotreba_nt_mwh': spotreba_nt_mwh,
                'celkova_spotreba_mwh': celkova_spotreba_mwh,
                # Jednotkové ceny
                'jednotkova_cena_elektriny_vt': jednotkova_cena_elektriny_vt,
                'jednotkova_cena_elektriny_nt': jednotkova_cena_elektriny_nt,
                'jednotkova_cena_distribuce_vt': jednotkova_cena_distribuce_vt,
                'jednotkova_cena_distribuce_nt': jednotkova_cena_distribuce_nt,
                'jednotkova_cena_systemove_sluzby': jednotkova_cena_systemove_sluzby,
                'jednotkova_cena_poze': jednotkova_cena_poze,
                'jednotkova_cena_dan': jednotkova_cena_dan
            })

        # Vybraz šablonu pro přílohu 2 na základě fakturovat_jen_distribuci
        if faktura and faktura.fakturovat_jen_distribuci:
            priloha2_template = "print/priloha2_jen_distribuce.html"
        else:
            priloha2_template = "print/priloha2.html"

        priloha2_html = render_template(priloha2_template,
                                       stredisko=stredisko_obj,
                                       obdobi=obdobi,
                                       faktura=faktura,
                                       dodavatel=dodavatel,
                                       vypocty_data=vypocty_data)

        # 4. KOMBINUJ HTML a přidej page-break styly
        combined_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                .page-break {{ page-break-before: always; }}
            </style>
        </head>
        <body>
            {faktura_html}
            <div class="page-break">{priloha1_html}</div>
            <div class="page-break">{priloha2_html}</div>
        </body>
        </html>
        """

        # 5. VYGENERUJ PDF pomocí WeasyPrint
        print("[INFO] Převádím kombinovaný HTML na PDF pomocí WeasyPrint...")
        if WEASYPRINT_AVAILABLE:
            try:
                final_pdf = _safe_weasyprint_convert(combined_html)
                print(f"[SUCCESS] Kompletní PDF vygenerováno pomocí HTML šablon! ({len(final_pdf)} bytů)")
                print("[INFO] Obsahuje: HTML faktura + HTML příloha 1 + HTML příloha 2")
                print("[SUCCESS] Kompletní PDF úspěšně vygenerováno")
            except Exception as weasy_error:
                raise Exception(f"WeasyPrint error in kompletni PDF: {weasy_error}")
        else:
            raise Exception("WeasyPrint není dostupný pro kompletní PDF")

        # Sestavení názvu souboru
        cislo_faktury = faktura.cislo_faktury if faktura and faktura.cislo_faktury else "faktura"
        nazev_faktury = stredisko.nazev_faktury if stredisko and stredisko.nazev_faktury else ""

        # Formát: {nazev_faktury}_{cislo_faktury}_{mesic}-{rok}.pdf nebo {cislo_faktury}_{mesic}-{rok}.pdf
        if nazev_faktury:
            filename = f"{nazev_faktury}_{cislo_faktury}_{mesic:02d}-{rok}.pdf"
        else:
            filename = f"{cislo_faktury}_{mesic:02d}-{rok}.pdf"

        response = make_response(final_pdf)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'inline; filename={filename}'
        return response

    except Exception as e:
        print(f"[ERROR] Chyba při generování kompletního PDF: {str(e)}")
        return f"Chyba při generování kompletního PDF: {str(e)}", 500

# ==== KONEC SOUBORU ====
