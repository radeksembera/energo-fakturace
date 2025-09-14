from flask import Blueprint, render_template, render_template_string, request, redirect, url_for, session, flash, make_response, send_file
from models import db, Stredisko, Faktura, ZalohovaFaktura, InfoDodavatele, InfoOdberatele, InfoVystavovatele, VypocetOM, OdberneMisto, Odečet, ObdobiFakturace
# Alias pro zpětnou kompatibilitu s kódem bez diakritiky
Odecet = Odečet
from datetime import datetime
import io

# [OK] REPORTLAB IMPORTS
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from file_helpers import get_faktury_path, get_faktura_filenames, check_faktury_exist
from flask import make_response
from reportlab.platypus import BaseDocTemplate, PageTemplate, Frame
from reportlab.platypus.doctemplate import PageTemplate

# Import kompatibilní verze PDF knihovny
try:
    from pypdf import PdfReader, PdfWriter
    PDF_VERSION = 'pypdf'
except ImportError:
    try:
        from PyPDF2 import PdfReader, PdfWriter
        PDF_VERSION = 'pyPDF2_new'
    except ImportError:
        # Fallback pro starší PyPDF2
        from PyPDF2 import PdfFileReader as PdfReader, PdfFileWriter as PdfWriter
        PDF_VERSION = 'pyPDF2_old'

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

def _get_faktura_pdf_bytes(stredisko_id, rok, mesic):
    """Pomocná funkce - vrací PDF faktury jako bytes"""
    print(f"[DEBUG] Začínám generování PDF faktury pro středisko {stredisko_id}, období {rok}/{mesic}")
    
    try:
        data, error = get_faktura_data(stredisko_id, rok, mesic)
        if error:
            raise Exception(f"Chyba při načítání dat faktury: {error}")
        print("[DEBUG] Data faktury úspěšně načtena")
        
        # Vygeneruj HTML obsah pomocí šablony
        html_content = render_template("print/faktura.html", 
                                     stredisko=data['stredisko'],
                                     obdobi=data['obdobi'],
                                     faktura=data['faktura'],
                                     zaloha=data['zaloha'],
                                     dodavatel=data['dodavatel'],
                                     odberatel=data['odberatel'],
                                     rekapitulace=data['rekapitulace'],
                                     zaklad_bez_dph=data['zaklad_bez_dph'],
                                     castka_dph=data['castka_dph'],
                                     celkem_vc_dph=data['celkem_vc_dph'],
                                     zaloha_celkem_vc_dph=data['zaloha_celkem_vc_dph'],
                                     zaloha_hodnota=data['zaloha_hodnota'],
                                     zaloha_dph=data['zaloha_dph'],
                                     k_platbe=data['k_platbe'],
                                     sazba_dph=data['sazba_dph'],
                                     sazba_dph_procenta=data['sazba_dph_procenta'])
        print(f"[DEBUG] HTML šablona vygenerována, délka: {len(html_content)} znaků")

        # Používej přímo jednoduchý ReportLab přístup (jako u přílohy 2)
        print("[INFO] Generuji PDF pomocí ReportLab podle HTML šablony")
        try:
            return _generate_simple_faktura_pdf(data)
        except Exception as reportlab_error:
            print(f"[ERROR] ReportLab generování selhalo: {reportlab_error}")
            raise reportlab_error
            
    except Exception as e:
        print(f"[ERROR] Obecná chyba v _get_faktura_pdf_bytes: {e}")
        import traceback
        traceback.print_exc()
        raise e


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
    
    # Vlastní styly
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Title'],
        fontSize=24,
        fontName=bold_font,
        textColor=colors.blue,
        spaceAfter=5
    )
    
    subtitle_style = ParagraphStyle(
        'Subtitle',
        parent=styles['Normal'],
        fontSize=12,
        fontName=base_font,
        textColor=colors.grey,
        spaceAfter=15
    )
    
    # Hlavička faktury
    story.append(Paragraph("FAKTURA", title_style))
    story.append(Paragraph("DAŇOVÝ DOKLAD", subtitle_style))
    
    # Dodavatel a odběratel v tabulce vedle sebe
    header_data = [
        [
            # Levý sloupec - Dodavatel
            [
                Paragraph(f"<b>{data['dodavatel'].nazev_sro if data['dodavatel'] else 'Your energy, s.r.o.'}</b>", styles['Normal']),
                Paragraph(f"{data['dodavatel'].adresa_radek_1 if data['dodavatel'] else 'Italská 2584/69'}", styles['Normal']),
                Paragraph(f"{data['dodavatel'].adresa_radek_2 if data['dodavatel'] else '120 00 Praha 2 - Vinohrady'}", styles['Normal']),
                Paragraph(f"<b>DIČ:</b> {data['dodavatel'].dic_sro if data['dodavatel'] else 'CZ24833851'}", styles['Normal']),
                Paragraph(f"<b>IČO:</b> {data['dodavatel'].ico_sro if data['dodavatel'] else '24833851'}", styles['Normal']),
                Spacer(1, 5),
                Paragraph(f"<b>Banka:</b> {data['dodavatel'].banka if data['dodavatel'] else 'Raiffeisenbank a.s. CZK'}", styles['Normal']),
                Paragraph(f"<b>Č.úč.:</b> {data['dodavatel'].cislo_uctu if data['dodavatel'] else '5041011366/5500'}", styles['Normal']),
                Paragraph(f"<b>IBAN:</b> {data['dodavatel'].iban if data['dodavatel'] else 'CZ1055000000005041011366'}", styles['Normal']),
                Paragraph(f"<b>SWIFT/BIC:</b> {data['dodavatel'].swift if data['dodavatel'] else 'RZBCCZPP'}", styles['Normal'])
            ],
            # Pravý sloupec - Faktura info a odběratel
            [
                Paragraph(f"<b>Faktura č. {data['faktura'].cislo_faktury if data['faktura'] else ''}</b>", styles['Heading2']),
                Paragraph(f"<b>Konst. symbol:</b> {data['faktura'].konstantni_symbol if data['faktura'] else ''}", styles['Normal']),
                Paragraph(f"<b>VS:</b> {data['faktura'].variabilni_symbol if data['faktura'] else ''}", styles['Normal']),
                Spacer(1, 10),
                Paragraph("<b>Odběratel:</b>", styles['Normal']),
                Paragraph(f"<b>{data['odberatel'].nazev_sro if data['odberatel'] else ''}</b>", styles['Normal']),
                Paragraph(f"{data['odberatel'].adresa_radek_1 if data['odberatel'] else ''}", styles['Normal']),
                Paragraph(f"{data['odberatel'].adresa_radek_2 if data['odberatel'] else ''}", styles['Normal']),
                Paragraph(f"<b>IČO:</b> {data['odberatel'].ico_sro if data['odberatel'] else ''}", styles['Normal']),
                Paragraph(f"<b>DIČ:</b> {data['odberatel'].dic_sro if data['odberatel'] else ''}", styles['Normal']),
                Spacer(1, 10),
                Paragraph(f"<b>Středisko:</b> {data['stredisko'].stredisko} {data['stredisko'].nazev_strediska}", styles['Normal']),
                Paragraph(f"{data['stredisko'].stredisko_mail if data['stredisko'].stredisko_mail else 'info@yourenergy.cz'}", styles['Normal'])
            ]
        ]
    ]
    
    header_table = Table(header_data, colWidths=[90*mm, 90*mm])
    header_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, 0), 'LEFT'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('FONTNAME', (0, 0), (-1, -1), base_font)
    ]))
    story.append(header_table)
    story.append(Spacer(1, 20))
    
    # Dodací a platební podmínky
    story.append(Paragraph("Dodací a platební podmínky", styles['Heading2']))
    
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
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3)
    ]))
    story.append(podminky_table)
    story.append(Spacer(1, 20))
    
    # Rekapitulace
    story.append(Paragraph("Rekapitulace", styles['Heading2']))
    
    # Tabulka rekapitulace
    rekap_data = [['Položka', 'Částka bez DPH', 'DPH', 'Částka s DPH']]
    
    # Přidej položky z rekapitulace
    for key, value in data['rekapitulace'].items():
        if value != 0:  # Pouze nenulové položky
            nazev = key.replace('_', ' ').title()
            dph_castka = value * (data['sazba_dph'] - 1)  # DPH část
            s_dph = value * data['sazba_dph']  # S DPH
            rekap_data.append([
                nazev,
                f"{value:.2f} Kč",
                f"{dph_castka:.2f} Kč", 
                f"{s_dph:.2f} Kč"
            ])
    
    # Součtové řádky
    rekap_data.append(['', '', '', ''])  # Prázdný řádek
    rekap_data.append(['CELKEM', f"{data['zaklad_bez_dph']:.2f} Kč", f"{data['castka_dph']:.2f} Kč", f"{data['celkem_vc_dph']:.2f} Kč"])
    
    if data['zaloha_celkem_vc_dph'] > 0:
        rekap_data.append(['Uhrazené zálohy', '', '', f"-{data['zaloha_celkem_vc_dph']:.2f} Kč"])
        rekap_data.append(['K PLATBĚ', '', '', f"{data['k_platbe']:.2f} Kč"])
    
    rekap_table = Table(rekap_data, colWidths=[80*mm, 35*mm, 35*mm, 35*mm])
    rekap_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
        ('FONTNAME', (0, 0), (-1, 0), bold_font),
        ('FONTNAME', (0, -3), (-1, -1), bold_font),  # Poslední 3 řádky tučně
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('FONTNAME', (0, 0), (-1, -1), base_font)
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
    try:
        pdf_bytes = _get_faktura_pdf_bytes(stredisko_id, rok, mesic)
        
        return send_file(
            io.BytesIO(pdf_bytes),
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f'faktura_{stredisko_id}_{rok}_{mesic:02d}.pdf'
        )
        
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
    """Generuje PDF zálohovou fakturu"""
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

        # Načti všechna potřebná data
        zaloha = ZalohovaFaktura.query.filter_by(stredisko_id=stredisko_id, obdobi_id=obdobi.id).first()
        dodavatel = InfoDodavatele.query.filter_by(stredisko_id=stredisko_id).first()
        odberatel = InfoOdberatele.query.first()
        vystavovatel = InfoVystavovatele.query.filter_by(stredisko_id=stredisko_id).first()

        # Vytvoř PDF s UTF-8 kódováním
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, 
                              rightMargin=20*mm, leftMargin=20*mm,
                              topMargin=20*mm, bottomMargin=20*mm)
        
        story = []
        styles = getSampleStyleSheet()
        font_registered = False  # Inicializace proměnné
        
        # [OK] REGISTRUJ ČESKÉ FONTY
        try:
            # Pokus o registraci českých fontů
            from reportlab.pdfbase.ttfonts import TTFont
            from reportlab.lib.fonts import addMapping
            
            # Pro Windows - zkus najít české fonty
            import os
            font_paths = [
                'C:/Windows/Fonts/arial.ttf',
                'C:/Windows/Fonts/calibri.ttf',
                '/System/Library/Fonts/Arial.ttf',  # macOS
                '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'  # Linux
            ]
            
            font_registered = False
            for font_path in font_paths:
                if os.path.exists(font_path):
                    try:
                        pdfmetrics.registerFont(TTFont('CzechFont', font_path))
                        font_registered = True
                        break
                    except:
                        continue
            
            if font_registered:
                # Nastav český font pro styly
                styles['Normal'].fontName = 'CzechFont'
                styles['Heading1'].fontName = 'CzechFont'
                styles['Heading2'].fontName = 'CzechFont'
                styles['Title'].fontName = 'CzechFont'
        except:
            # Fallback - použij základní fonty s UTF-8
            pass
        
        # [OK] HLAVIČKA - STEJNÁ JAKO HTML
        hlavicka_data = [
            [
                # Levá strana - dodavatel
                [
                    Paragraph("<b>ZÁLOHOVÁ FAKTURA - DAŇOVÝ DOKLAD</b>", styles['Heading1']),
                    Paragraph(f"<b>{dodavatel.nazev_sro if dodavatel else 'Your energy, s.r.o.'}</b>", styles['Normal']),
                    Paragraph(f"{dodavatel.adresa_radek_1 if dodavatel else 'Italská 2584/69'}", styles['Normal']),
                    Paragraph(f"{dodavatel.adresa_radek_2 if dodavatel else '120 00 Praha 2 - Vinohrady'}", styles['Normal']),
                    Paragraph(f"<b>DIČ</b> {dodavatel.dic_sro if dodavatel else 'CZ24833851'}", styles['Normal']),
                    Paragraph(f"<b>IČO</b> {dodavatel.ico_sro if dodavatel else '24833851'}", styles['Normal']),
                    Paragraph("", styles['Normal']),  # Spacer
                    Paragraph(f"<b>Banka:</b> {dodavatel.banka if dodavatel else 'Bankovní účet Raiffeisenbank a.s. CZK'}", styles['Normal']),
                    Paragraph(f"<b>Č.úč.</b> {dodavatel.cislo_uctu if dodavatel else '5041011366/5500'}", styles['Normal']),
                    Paragraph(f"<b>IBAN</b> {dodavatel.iban if dodavatel else 'CZ1055000000005041011366'}", styles['Normal']),
                    Paragraph(f"<b>SWIFT/BIC</b> {dodavatel.swift if dodavatel else 'RZBCCZPP'}", styles['Normal']),
                ],
                # Pravá strana - faktura info + odběratel
                [
                    Paragraph(f"<b>Číslo {zaloha.cislo_zalohove_faktury if zaloha else ''}</b>", styles['Heading2']),
                    Paragraph("", styles['Normal']),  # Spacer
                    Paragraph(f"<b>konst. symbol</b> {zaloha.konstantni_symbol if zaloha else ''}", styles['Normal']),
                    Paragraph(f"<b>VS</b> {zaloha.variabilni_symbol if zaloha else ''}", styles['Normal']),
                    Paragraph("", styles['Normal']),  # Spacer
                    Paragraph("Objednávka:", styles['Normal']),
                    Paragraph("", styles['Normal']),  # Spacer pro box
                    # Odběratel box
                    Paragraph("<b>Odběratel:</b>", styles['Normal']),
                    Paragraph(f"<b>{odberatel.nazev_sro if odberatel else ''}</b>", styles['Normal']),
                    Paragraph(f"{odberatel.adresa_radek_1 if odberatel else ''}", styles['Normal']),
                    Paragraph(f"{odberatel.adresa_radek_2 if odberatel else ''}", styles['Normal']),
                    Paragraph(f"<b>IČO:</b> {odberatel.ico_sro if odberatel else ''}", styles['Normal']),
                    Paragraph(f"<b>DIČ:</b> {odberatel.dic_sro if odberatel else ''}", styles['Normal']),
                    Paragraph("", styles['Normal']),  # Spacer
                    Paragraph(f"<b>Středisko:</b> {stredisko.stredisko} {stredisko.nazev_strediska}", styles['Normal']),
                    Paragraph(f"{stredisko.stredisko_mail if stredisko.stredisko_mail else 'info@yourenergy.cz'}", styles['Normal']),
                ]
            ]
        ]
        
        hlavicka_table = Table(hlavicka_data, colWidths=[250, 250])
        hlavicka_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ]))
        
        story.append(hlavicka_table)
        story.append(Spacer(1, 20))
        
        # [OK] DODACÍ A PLATEBNÍ PODMÍNKY
        podmínky_data = [
            ['Dodací a platební podmínky', '', ''],
            ['Datum splatnosti', 'Datum vystavení', 'Forma úhrady'],
            [
                zaloha.datum_splatnosti.strftime('%d.%m.%Y') if zaloha and zaloha.datum_splatnosti else '',
                zaloha.datum_vystaveni.strftime('%d.%m.%Y') if zaloha and zaloha.datum_vystaveni else '',
                zaloha.forma_uhrady if zaloha else ''
            ]
        ]
        
        podmínky_table = Table(podmínky_data, colWidths=[150, 150, 150])
        podmínky_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightblue),
            ('FONTNAME', (0, 0), (-1, 0), 'CzechFont' if font_registered else 'Helvetica-Bold'),
            ('BACKGROUND', (0, 1), (-1, 1), colors.lightgrey),
            ('FONTNAME', (0, 1), (-1, 1), 'CzechFont' if font_registered else 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTNAME', (0, 0), (-1, -1), 'CzechFont' if font_registered else 'Helvetica'),
        ]))
        
        story.append(podmínky_table)
        story.append(Spacer(1, 20))
        
        # [OK] ZÁLOHOVÁ ČÁSTKA
        if zaloha and zaloha.zaloha:
            sazba_dph = 0.21  # 21% DPH
            zaloha_vc_dph = float(zaloha.zaloha)
            zaloha_bez_dph = zaloha_vc_dph / (1 + sazba_dph)
            castka_dph = zaloha_vc_dph - zaloha_bez_dph
            
            zaloha_data = [
                ['Popis', 'Základ daně', 'Sazba DPH', 'Částka DPH', 'Celkem vč. DPH'],
                [f'Záloha na období {obdobi.rok}/{obdobi.mesic:02d}', f'{zaloha_bez_dph:.2f}', '21', f'{castka_dph:.2f}', f'{zaloha_vc_dph:.2f}'],
                ['CELKEM', f'{zaloha_bez_dph:.2f}', '', f'{castka_dph:.2f}', f'{zaloha_vc_dph:.2f}']
            ]
            
            zaloha_table = Table(zaloha_data, colWidths=[180, 80, 60, 80, 80])
            zaloha_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.lightblue),
                ('FONTNAME', (0, 0), (-1, 0), 'CzechFont' if font_registered else 'Helvetica-Bold'),
                ('BACKGROUND', (0, 2), (-1, 2), colors.lightgrey),  # CELKEM řádek
                ('FONTNAME', (0, 2), (-1, 2), 'CzechFont' if font_registered else 'Helvetica-Bold'),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('ALIGN', (1, 1), (-1, -1), 'RIGHT'),  # Čísla vpravo
                ('ALIGN', (0, 0), (0, -1), 'LEFT'),   # Názvy vlevo
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('FONTNAME', (0, 0), (-1, -1), 'CzechFont' if font_registered else 'Helvetica'),
            ]))
            
            story.append(zaloha_table)
            story.append(Spacer(1, 20))
            
            # K PLATBĚ
            story.append(Paragraph(f"<b>K platbě celkem Kč {zaloha_vc_dph:.2f}</b>", styles['Title']))
            story.append(Spacer(1, 15))
        
        # [OK] VYSTAVOVATEL
        if vystavovatel:
            story.append(Paragraph(f"<b>Vystavil:</b> {vystavovatel.jmeno_vystavitele if vystavovatel.jmeno_vystavitele else ''}", styles['Normal']))
            story.append(Paragraph(f"<b>Telefon:</b> {vystavovatel.telefon_vystavitele if vystavovatel.telefon_vystavitele else ''}", styles['Normal']))
            story.append(Paragraph(f"<b>Email:</b> {vystavovatel.email_vystavitele if vystavovatel.email_vystavitele else ''}", styles['Normal']))
        
        # [OK] GENERUJ PDF
        doc.build(story)
        
        pdf = buffer.getvalue()
        buffer.close()
        
        response = make_response(pdf)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'inline; filename=zalohova_{rok}_{mesic:02d}.pdf'
        
        return response
        
    except Exception as e:
        flash(f"[ERROR] Chyba při generování PDF: {str(e)}")
        return redirect(url_for('fakturace.fakturace', stredisko_id=stredisko_id))

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
    """Generuje PDF přílohu 1 - hodnoty měření s automatickým stránkováním"""
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

        # Načti základní data
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

        # [OK] REGISTRACE FONTŮ
        font_registered = False
        try:
            from reportlab.pdfbase.ttfonts import TTFont
            import os
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

        # [OK] FUNKCE PRO VYTVOŘENÍ STORY (obsahu)
        def create_story():
            story = []
            styles = getSampleStyleSheet()
            
            if font_registered:
                styles['Normal'].fontName = 'CzechFont'
                styles['Heading1'].fontName = 'CzechFont'
                styles['Heading2'].fontName = 'CzechFont'
                styles['Title'].fontName = 'CzechFont'
            
            # HLAVIČKA
            story.append(Paragraph(f"<b>Příloha 1 - Hodnoty měření k dokladu</b>", styles['Title']))
            
            company_info = f"{dodavatel.nazev_sro if dodavatel else 'Your energy, s.r.o.'}, " \
                          f"{dodavatel.adresa_radek_1 if dodavatel else 'Italská 2584/69'} " \
                          f"{dodavatel.adresa_radek_2 if dodavatel else '120 00 Praha 2 - Vinohrady'}, " \
                          f"DIČ {dodavatel.dic_sro if dodavatel else 'CZ24833851'} " \
                          f"IČO {dodavatel.ico_sro if dodavatel else '24833851'}"
            
            story.append(Paragraph(company_info, styles['Normal']))
            story.append(Spacer(1, 20))

            # PROCHÁZEJ ODBĚRNÁ MÍSTA
            if odecty:
                for odecet, om in odecty:
                    # Název odběrného místa
                    om_nazev = f"<b>Odběrné místo: {odecet.oznaceni or ''} {om.nazev_om if om else ''}</b>"
                    story.append(Paragraph(om_nazev, styles['Normal']))
                    story.append(Spacer(1, 6))
                    
                    # Tabulka
                    data = [
                        ['Měření', 'Od', 'Do', 'Počátek', 'Konec', 'Spotřeba', 'MJ', 'Poznámka']
                    ]
                    
                    # Období měření
                    od_text = odecet.zacatek_periody_mereni.strftime('%d.%m.%Y') if odecet.zacatek_periody_mereni else ''
                    do_text = odecet.konec_periody_mereni.strftime('%d.%m.%Y') if odecet.konec_periody_mereni else ''
                    
                    # VT řádek
                    data.append([
                        'Spotřeba VT',
                        od_text,
                        do_text,
                        f"{float(odecet.pocatecni_hodnota_vt or 0):,.2f}".replace(',', ' '),
                        f"{float(odecet.hodnota_odectu_vt or 0):,.2f}".replace(',', ' '),
                        f"{float(odecet.spotreba_vt or 0):,.2f}".replace(',', ' '),
                        'kWh',
                        odecet.priznak if odecet.priznak else ''
                    ])
                    
                    # NT řádek (vždy zobrazit)
                    data.append([
                        'Spotřeba NT',
                        od_text,
                        do_text,
                        f"{float(odecet.pocatecni_hodnota_nt or 0):,.2f}".replace(',', ' '),
                        f"{float(odecet.hodnota_odectu_nt or 0):,.2f}".replace(',', ' '),
                        f"{float(odecet.spotreba_nt or 0):,.2f}".replace(',', ' '),
                        'kWh',
                        odecet.priznak if odecet.priznak else ''
                    ])

                    # Tabulka
                    table = Table(data, colWidths=[65, 55, 55, 65, 65, 65, 30, 70])
                    table.setStyle(TableStyle([
                        ('FONTSIZE', (0, 0), (-1, -1), 8),
                        ('FONTNAME', (0, 0), (-1, -1), 'CzechFont' if font_registered else 'Helvetica'),
                        ('FONTNAME', (0, 0), (-1, 0), 'CzechFont' if font_registered else 'Helvetica-Bold'),
                        ('ALIGN', (0, 0), (2, -1), 'LEFT'),
                        ('ALIGN', (3, 0), (-2, -1), 'RIGHT'),
                        ('ALIGN', (-1, 0), (-1, -1), 'LEFT'),
                        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                        ('LEFTPADDING', (0, 0), (-1, -1), 3),
                        ('RIGHTPADDING', (0, 0), (-1, -1), 3),
                        ('TOPPADDING', (0, 0), (-1, -1), 2),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
                        ('LINEBELOW', (0, 0), (-1, 0), 0.5, colors.black),
                    ]))

                    story.append(table)
                    story.append(Spacer(1, 15))
            else:
                story.append(Paragraph("Nejsou k dispozici žádné odečty pro vybrané období.", styles['Normal']))
            
            return story

        # [OK] 1. PRŮCHOD - zjistíme počet stránek
        temp_buffer = io.BytesIO()
        temp_doc = SimpleDocTemplate(temp_buffer, pagesize=A4, 
                                  rightMargin=15*mm, leftMargin=15*mm,
                                  topMargin=20*mm, bottomMargin=20*mm)
        temp_story = create_story()
        temp_doc.build(temp_story)
        
        # Vypočítáme počet stránek
        temp_buffer.seek(0)
        try:
            reader = create_pdf_reader(temp_buffer)
            total_pages = len(reader.pages)
        except:
            # Fallback - odhad počtu stránek
            total_pages = max(1, len(odecty) // 3)  # Odhad: 3 OM na stránku
        
        # [OK] 2. PRŮCHOD - vytvoříme finální PDF se stránkováním
        buffer = io.BytesIO()
        
        # Globální proměnná pro počet stránek
        TOTAL_PAGES = total_pages
        
        # Custom template s footer funkcí
        def add_page_number(canvas, doc):
            """Přidá stránkování do footeru"""
            canvas.saveState()
            canvas.setFont('CzechFont' if font_registered else 'Helvetica', 9)
            page_num = f"Strana {doc.page} z {TOTAL_PAGES}"
            # Vycentrovat na spodu stránky
            text_width = canvas.stringWidth(page_num, 'CzechFont' if font_registered else 'Helvetica', 9)
            x = (A4[0] - text_width) / 2
            canvas.drawString(x, 15*mm, page_num)
            canvas.restoreState()
        
        # Vytvoř finální dokument
        from reportlab.platypus import BaseDocTemplate, PageTemplate, Frame
        doc = BaseDocTemplate(buffer, pagesize=A4, 
                            rightMargin=15*mm, leftMargin=15*mm,
                            topMargin=20*mm, bottomMargin=30*mm)  # Větší spodní okraj pro stránkování
        
        frame = Frame(15*mm, 30*mm, A4[0]-30*mm, A4[1]-50*mm, id='normal')
        template = PageTemplate(id='later', frames=frame, onPage=add_page_number)
        doc.addPageTemplates([template])
        
        # Vytvoř story znovu
        final_story = create_story()
        doc.build(final_story)
        
        pdf = buffer.getvalue()
        buffer.close()
        temp_buffer.close()
        
        response = make_response(pdf)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'inline; filename=priloha1_{rok}_{mesic:02d}.pdf'
        
        return response
        
    except Exception as e:
        flash(f"[ERROR] Chyba při generování PDF: {str(e)}")
        return redirect(url_for('fakturace.fakturace', stredisko_id=stredisko_id))
    

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
        .filter(VypocetOM.id > 0)\
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
        
        # Celková suma za OM - převeď všechny hodnoty na float
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
        html_content = render_template("print/priloha2.html", 
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
        html_content = render_template("print/priloha2.html", 
                            stredisko=stredisko,
                            obdobi=obdobi,
                            faktura=faktura,
                            dodavatel=dodavatel,
                            vypocty_data=vypocty_data)
        
        response = make_response(html_content)
        response.headers['Content-Type'] = 'text/html; charset=utf-8'
        
        return response


def _get_priloha2_pdf_bytes(stredisko_id, rok, mesic):
    """Interní funkce pro získání PDF bytů přílohy 2 (pro kompletní fakturu) - čistý ReportLab"""
    try:
        # Najdi období
        obdobi = ObdobiFakturace.query.filter_by(
            stredisko_id=stredisko_id, rok=rok, mesic=mesic
        ).first()
        if not obdobi:
            raise ValueError(f"Období {rok}/{mesic:02d} nenalezeno")

        # Načti základní data
        faktura = Faktura.query.filter_by(stredisko_id=stredisko_id, obdobi_id=obdobi.id).first()
        dodavatel = InfoDodavatele.query.filter_by(stredisko_id=stredisko_id).first()
        stredisko = Stredisko.query.get(stredisko_id)
        
        # Načti výpočty
        vypocty_om = db.session.query(VypocetOM, OdberneMisto)\
            .join(OdberneMisto, VypocetOM.odberne_misto_id == OdberneMisto.id)\
            .filter(VypocetOM.obdobi_id == obdobi.id)\
            .filter(OdberneMisto.stredisko_id == stredisko_id)\
            .order_by(OdberneMisto.cislo_om)\
            .all()
        
        if not vypocty_om:
            raise ValueError("Nejsou výpočty pro vybrané období")

        # Použij tu istú logiku ako v novej funkcii - čistý ReportLab
        return _generate_priloha2_pdf_reportlab(stredisko, obdobi, faktura, dodavatel, vypocty_om)
        
    except Exception as e:
        print(f"[ERROR] Chyba v _get_priloha2_pdf_bytes: {e}")
        import traceback
        traceback.print_exc()
        raise


def _generate_priloha2_pdf_reportlab(stredisko, obdobi, faktura, dodavatel, vypocty_om):
    """Fallback funkce pro generování PDF přílohy 2 pomocí ReportLab"""
    import io
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    
    print("[DEBUG] Zacinam ReportLab fallback pro prilohu 2")
    
    # Vytvoř PDF dokument
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, 
                          rightMargin=15*mm, leftMargin=15*mm,
                          topMargin=20*mm, bottomMargin=20*mm)
    
    story = []
    styles = getSampleStyleSheet()
    
    # Nadpis
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        spaceAfter=20,
        alignment=1  # Center
    )
    story.append(Paragraph("PŘÍLOHA Č. 2", title_style))
    story.append(Paragraph("Rozpis položek za odběrná místa", styles['Heading2']))
    story.append(Spacer(1, 20))
    
    # Informace o období
    story.append(Paragraph(f"<b>Středisko:</b> {stredisko.nazev_strediska}", styles['Normal']))
    story.append(Paragraph(f"<b>Období:</b> {obdobi.rok}/{obdobi.mesic:02d}", styles['Normal']))
    story.append(Spacer(1, 15))
    
    # Tabulka s výpočty
    table_data = [['OM', 'Spotřeba VT', 'Spotřeba NT', 'Celkem za OM']]
    
    for vypocet, om in vypocty_om[:10]:  # Omez na 10 řádků kvůli místě
        # Vypočítej minimum z POZE
        poze_minimum = min(float(vypocet.poze_dle_jistice or 0), float(vypocet.poze_dle_spotreby or 0))
        
        # Celková suma za OM
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
        
        # Načti odečet pro získání spotřeb - zjednodušená verze
        spotreba_vt = 0  # Placeholder - v plné verzi by se načítalo z Odecet
        spotreba_nt = 0  # Placeholder - v plné verzi by se načítalo z Odecet
        
        table_data.append([
            str(om.cislo_om) if om.cislo_om else 'N/A',
            f"{spotreba_vt:.3f} MWh",
            f"{spotreba_nt:.3f} MWh", 
            f"{celkem_om:.2f} Kč"
        ])
    
    if len(vypocty_om) > 10:
        table_data.append(['...', '...', '...', '...'])
        table_data.append([f'Celkem {len(vypocty_om)} odběrných míst', '', '', ''])
    
    table = Table(table_data)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('ALIGN', (3, 0), (3, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    story.append(table)
    
    story.append(Spacer(1, 20))
    story.append(Paragraph("<i>Poznámka: Toto je zjednodušená verze přílohy 2 vygenerovaná pomocí ReportLab fallback.</i>", styles['Normal']))
    
    # Vytvoř PDF
    doc.build(story)
    pdf_data = buffer.getvalue()
    buffer.close()
    
    print(f"[DEBUG] ReportLab PDF prilohy 2 vygenerovan, velikost: {len(pdf_data)} bytu")
    return pdf_data


@print_bp.route("/<int:stredisko_id>/<int:rok>-<int:mesic>/priloha2/pdf")
def priloha2_pdf_nova(stredisko_id, rok, mesic):
    """Generování PDF přílohy 2 s daty z databáze"""
    if not session.get("user_id"):
        return redirect("/login")

    try:
        stredisko = Stredisko.query.get_or_404(stredisko_id)
        if stredisko.user_id != session["user_id"]:
            return "Nepovolený přístup", 403

        # Najdi období
        obdobi = ObdobiFakturace.query.filter_by(
            stredisko_id=stredisko_id, rok=rok, mesic=mesic
        ).first()
        if not obdobi:
            return "Období nenalezeno", 404
            
        # Načti data z databáze
        vypocty_om = db.session.query(VypocetOM, OdberneMisto)\
            .join(OdberneMisto, VypocetOM.odberne_misto_id == OdberneMisto.id)\
            .filter(VypocetOM.obdobi_id == obdobi.id)\
            .filter(OdberneMisto.stredisko_id == stredisko_id)\
            .distinct(OdberneMisto.id)\
            .order_by(OdberneMisto.id, OdberneMisto.cislo_om)\
            .all()

        if not vypocty_om:
            return "Nejsou výpočty pro vybrané období", 404

        # Načti fakturu pro období
        faktura = Faktura.query.filter_by(stredisko_id=stredisko_id, obdobi_id=obdobi.id).first()
        
        # Generování PDF podle HTML šablony
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
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
                              rightMargin=40*mm, leftMargin=40*mm,
                              topMargin=20*mm, bottomMargin=20*mm)
        
        story = []
        styles = getSampleStyleSheet()
        
        # Nastav český font pro základní styly
        base_font = 'CzechFont' if font_registered else 'Helvetica'
        bold_font = 'CzechFont' if font_registered else 'Helvetica-Bold'
        
        if font_registered:
            styles['Normal'].fontName = base_font
            styles['Heading1'].fontName = base_font
            styles['Heading2'].fontName = base_font
            styles['Heading3'].fontName = base_font
        
        # Vlastní styly
        section_style = ParagraphStyle(
            'SectionTitle',
            parent=styles['Heading3'],
            fontSize=11,
            fontName=bold_font,
            spaceAfter=5,
            spaceBefore=20
        )
        
        total_style = ParagraphStyle(
            'Total',
            parent=styles['Normal'],
            fontSize=15,
            fontName=bold_font,
            alignment=2,  # Right align
            spaceAfter=20,
            spaceBefore=10
        )
        
        # Pro každé odběrné místo vytvoř vlastní stránku
        for i, (vypocet, om) in enumerate(vypocty_om):
            if i > 0:  # Přidej page break před každé další OM
                story.append(PageBreak())
            
            # Načti odečet pro spotřeby
            odecet = Odecet.query.filter_by(
                stredisko_id=stredisko_id,
                obdobi_id=obdobi.id,
                oznaceni=om.cislo_om.zfill(7) if om.cislo_om else None
            ).first()
            
            spotreba_vt = float(odecet.spotreba_vt or 0) if odecet else 0
            spotreba_nt = float(odecet.spotreba_nt or 0) if odecet else 0
            spotreba_vt_mwh = spotreba_vt / 1000  # Převod na MWh
            spotreba_nt_mwh = spotreba_nt / 1000
            celkova_spotreba_mwh = spotreba_vt_mwh + spotreba_nt_mwh
            
            # Výpočet jednotkových cen (zjednodušeno)
            jednotkova_cena_elektriny_vt = float(vypocet.platba_za_elektrinu_vt or 0) / spotreba_vt_mwh if spotreba_vt_mwh > 0 else 0
            jednotkova_cena_elektriny_nt = float(vypocet.platba_za_elektrinu_nt or 0) / spotreba_nt_mwh if spotreba_nt_mwh > 0 else 0
            jednotkova_cena_distribuce_vt = float(vypocet.platba_za_distribuci_vt or 0) / spotreba_vt_mwh if spotreba_vt_mwh > 0 else 0
            jednotkova_cena_distribuce_nt = float(vypocet.platba_za_distribuci_nt or 0) / spotreba_nt_mwh if spotreba_nt_mwh > 0 else 0
            jednotkova_cena_systemove_sluzby = float(vypocet.systemove_sluzby or 0) / celkova_spotreba_mwh if celkova_spotreba_mwh > 0 else 0
            jednotkova_cena_dan = float(vypocet.dan_z_elektriny or 0) / celkova_spotreba_mwh if celkova_spotreba_mwh > 0 else 0
            
            # POZE minimum
            poze_minimum = min(float(vypocet.poze_dle_jistice or 0), float(vypocet.poze_dle_spotreby or 0))
            jednotkova_cena_poze = poze_minimum / celkova_spotreba_mwh if celkova_spotreba_mwh > 0 else 0
            
            # Celková suma za OM
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
            
            # Informace o odběrném místě
            story.append(Paragraph(f"<b>Odběrné místo:</b> {om.cislo_om} {om.nazev_om or ''}", styles['Normal']))
            story.append(Paragraph(f"{stredisko.adresa or 'Nádražní 762/32, Praha 5 - Smíchov, PSČ 150 00'}", styles['Normal']))
            story.append(Paragraph(f"<b>EAN:</b> {om.ean_om or '859182403280020114'}", styles['Normal']))
            story.append(Spacer(1, 10))
            
            # Další informace
            fakturace_od = faktura.fakturace_od.strftime('%d.%m.%Y') if faktura and faktura.fakturace_od else '01.06.2025'
            fakturace_do = faktura.fakturace_do.strftime('%d.%m.%Y') if faktura and faktura.fakturace_do else '30.06.2025'
            
            story.append(Paragraph(f"<b>Distribuční sazba:</b> {om.distribucni_sazba_om or 'N/A'}", styles['Normal']))
            story.append(Paragraph(f"<b>Kategorie hlavního jističe:</b> {om.kategorie_jistice_om or 'N/A'}", styles['Normal']))
            story.append(Paragraph(f"<b>Hodnota hlavního jističe [A]:</b> {om.hodnota_jistice_om or 'N/A'}", styles['Normal']))
            story.append(Paragraph(f"<b>Období fakturace:</b> {fakturace_od} - {fakturace_do}", styles['Normal']))
            story.append(Spacer(1, 15))
            
            # Dodávka elektřiny
            story.append(Paragraph("Dodávka elektřiny", section_style))
            table_data = [
                ['Stálý plat', '1', '1', f"{float(vypocet.mesicni_plat or 0):.2f}", f"{float(vypocet.mesicni_plat or 0):.2f}"],
                ['Plat za silovou elektřinu v VT', f"{spotreba_vt_mwh:.4f}", 'MWh', f"{jednotkova_cena_elektriny_vt:.2f}", f"{float(vypocet.platba_za_elektrinu_vt or 0):.2f}"],
                ['Plat za silovou elektřinu v NT', f"{spotreba_nt_mwh:.4f}", 'MWh', f"{jednotkova_cena_elektriny_nt:.2f}", f"{float(vypocet.platba_za_elektrinu_nt or 0):.2f}"]
            ]
            
            table = Table(table_data, colWidths=[80*mm, 20*mm, 15*mm, 25*mm, 25*mm])
            table.setStyle(TableStyle([
                ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
                ('FONTNAME', (0, 0), (-1, -1), base_font),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('TOPPADDING', (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3)
            ]))
            story.append(table)
            
            # Distribuční služby
            story.append(Paragraph("Distribuční služby", section_style))
            table_data = [
                ['Měsíční plat', '1', '1', f"{float(vypocet.platba_za_jistic or 0):.2f}", f"{float(vypocet.platba_za_jistic or 0):.2f}"],
                ['Plat za elektřinu ve VT', f"{spotreba_vt_mwh:.4f}", 'MWh', f"{jednotkova_cena_distribuce_vt:.2f}", f"{float(vypocet.platba_za_distribuci_vt or 0):.2f}"],
                ['Plat za elektřinu ve NT', f"{spotreba_nt_mwh:.4f}", 'MWh', f"{jednotkova_cena_distribuce_nt:.2f}", f"{float(vypocet.platba_za_distribuci_nt or 0):.2f}"],
                ['Cena za systémové služby', f"{celkova_spotreba_mwh:.4f}", 'MWh', f"{jednotkova_cena_systemove_sluzby:.2f}", f"{float(vypocet.systemove_sluzby or 0):.2f}"],
                ['Podpora elekt. z podporovaných zdrojů energie', f"{celkova_spotreba_mwh:.4f}", 'MWh', f"{jednotkova_cena_poze:.2f}", f"{poze_minimum:.2f}"],
                ['Poplatek za nesíťovou infrastrukturu', '1', '1', f"{float(vypocet.nesitova_infrastruktura or 0):.2f}", f"{float(vypocet.nesitova_infrastruktura or 0):.2f}"]
            ]
            
            table = Table(table_data, colWidths=[80*mm, 20*mm, 15*mm, 25*mm, 25*mm])
            table.setStyle(TableStyle([
                ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
                ('FONTNAME', (0, 0), (-1, -1), base_font),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('TOPPADDING', (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3)
            ]))
            story.append(table)
            
            # Daň
            story.append(Paragraph("Daň", section_style))
            table_data = [
                ['Daň', f"{celkova_spotreba_mwh:.4f}", 'MWh', f"{jednotkova_cena_dan:.2f}", f"{float(vypocet.dan_z_elektriny or 0):.2f}"]
            ]
            
            table = Table(table_data, colWidths=[80*mm, 20*mm, 15*mm, 25*mm, 25*mm])
            table.setStyle(TableStyle([
                ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
                ('FONTNAME', (0, 0), (-1, -1), base_font),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('TOPPADDING', (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3)
            ]))
            story.append(table)
            
            # Čára a celkem
            story.append(Spacer(1, 10))
            story.append(Paragraph("<hr/>", styles['Normal']))
            story.append(Paragraph(f"Celkem: {celkem_om:.2f} Kč", total_style))
        
        # Přidej další důležité informace na konec dokumentu (VEN z for cyklu)
        story.append(PageBreak())
        
        # Nadpis pro další informace
        info_title_style = ParagraphStyle(
            'InfoTitle',
            parent=styles['Heading1'],
            fontSize=18,
            fontName=bold_font,
            spaceAfter=20,
            spaceBefore=20,
            alignment=1  # Center
        )
        
        info_heading_style = ParagraphStyle(
            'InfoHeading',
            parent=styles['Heading2'],
            fontSize=12,
            fontName=bold_font,
            spaceAfter=10,
            spaceBefore=15
        )
        
        story.append(Paragraph("Další důležité informace", info_title_style))
        
        # 1. Podíl zdrojů energie
        story.append(Paragraph("Podíl jednotlivých zdrojů nebo původů energie na celkové směsi paliv dodavatele v roce 2024", info_heading_style))
        
        energy_table_data = [
            ['Původ elektřiny', '% podíl'],
            ['Uhelné elektrárny (uhlí)', '44,69'],
            ['Jaderné elektrárny (jádro)', '42,82'],
            ['Podíl elektřiny vyrobené ze zemního plynu', '5,79'],
            ['Obnovitelné zdroje energie (OZE)', '6,4'],
            ['Druhotné zdroje', '0,16'],
            ['Ostatní zdroje', '0,14'],
            ['celkem', '100']
        ]
        
        energy_table = Table(energy_table_data, colWidths=[120*mm, 30*mm])
        energy_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (-1, 0), bold_font),
            ('FONTNAME', (0, 0), (-1, -1), base_font),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('BACKGROUND', (0, -1), (-1, -1), colors.lightgrey),
            ('FONTNAME', (0, -1), (-1, -1), bold_font)
        ]))
        story.append(energy_table)
        story.append(Spacer(1, 15))
        
        # 2. Informace o dopadech na životní prostředí
        story.append(Paragraph("Informace o dopadech výroby elektřiny na životní prostředí", info_heading_style))
        story.append(Paragraph("Informace o dopadech výroby elektřiny na životní prostředí jsou dostupné na internetových stránkách Ministerstva životního prostředí www.mzp.cz.", styles['Normal']))
        story.append(Spacer(1, 10))
        
        # 3. Reklamace
        story.append(Paragraph("Reklamace, řešení sporů", info_heading_style))
        story.append(Paragraph("Zákazník může k vyúčtování dodávek elektřiny a souvisejících služeb uplatnit reklamaci na adrese fakturace@venergie.cz nebo na adrese Východočeská energie s.r.o., V Celnici 1040/5, 110 00 Praha 1, ve lhůtě 30 dnů ode dne doručení. V případě vzniku sporu mezi zákazníkem a dodavatelem může zákazník podat návrh na rozhodnutí tohoto sporu podle § 17 odst. 7 energetického zákona, přitom musí postupovat podle správního řádu.", styles['Normal']))
        story.append(Spacer(1, 10))
        
        # 4. Změna dodavatele
        story.append(Paragraph("Změna dodavatele", info_heading_style))
        story.append(Paragraph("Zákazníci a spotřebitelé mají právo zvolit si a bezplatně změnit svého dodavatele. Každý zákazník se podpisem smlouvy zavázal dodržet její podmínky. Pokud je smlouva uzavřena na dobu určitou, je zákazník povinen tento závazek dodržet. Při ukončení smluvního vztahu je tedy nutné postupovat dle smlouvy, dodatku a všeobecných obchodních podmínek, které jsou nedílnou součástí každé smlouvy. Před změnou dodavatele je vhodné si zjistit, zda je změna dodavatele výhodná, a to nejen srovnáním ceny, ale i Obchodních podmínek dodavatele. Pro nezávislé porovnání cenových nabídek dodavatelů můžete využít například kalkulačku Energetického regulačního úřadu, kterou naleznete na adrese www.eru.cz.", styles['Normal']))
        story.append(Spacer(1, 10))
        
        # 5. Kontaktní údaje
        story.append(Paragraph("Důležité kontaktní údaje", info_heading_style))
        story.append(Paragraph("<b>Energetický regulační úřad</b>", styles['Normal']))
        story.append(Paragraph("adresa sídla: Masarykovo náměstí 5, 586 01 Jihlava<br/>telefonní číslo: 564 578 666 – ústředna<br/>adresa webových stránek: www.eru.cz<br/>adresa elektronické podatelny: podatelna@eru.cz", styles['Normal']))
        
        doc.build(story)
        pdf_data = buffer.getvalue()
        buffer.close()
        
        response = make_response(pdf_data)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'inline; filename=priloha2_{stredisko.nazev_strediska}_{rok}_{mesic:02d}.pdf'
        
        return response
        
    except Exception as e:
        return f"CHYBA v příloze 2: {str(e)}"

@print_bp.route("/<int:stredisko_id>/<int:rok>-<int:mesic>/priloha2/test")
def test_priloha2_route(stredisko_id, rok, mesic):
    """ÚPLNĚ JEDNODUCHÝ TEST - bez databáze"""
    return f"TEST ROUTE WORKS: stredisko={stredisko_id}, rok={rok}, mesic={mesic}"

@print_bp.route("/<int:stredisko_id>/<int:rok>-<int:mesic>/priloha2_backup/pdf")
def vygenerovat_prilohu2_pdf_backup(stredisko_id, rok, mesic):
    """ZÁLOHNÍ VERZE - příliš komplexní, způsobuje EOF chyby"""
    """Generuje PDF přílohu 2 - rozpis položek za odběrná místa s automatickým stránkováním a důležitými informacemi"""
    
    data, error = get_faktura_data(stredisko_id, rok, mesic)
    if error:
        return error

    try:
        # Načti výpočty
        vypocty_om = db.session.query(VypocetOM, OdberneMisto)\
            .join(OdberneMisto, VypocetOM.odberne_misto_id == OdberneMisto.id)\
            .filter(VypocetOM.id > 0)\
            .filter(OdberneMisto.stredisko_id == stredisko_id)\
            .order_by(OdberneMisto.cislo_om)\
            .all()
        
        if not vypocty_om:
            return "Nejsou k dispozici výpočty pro vybrané období.", 400

        # Načti vystavovatele pro důležité informace
        from models import InfoVystavovatele
        vystavovatel = InfoVystavovatele.query.filter_by(stredisko_id=stredisko_id).first()

        # [OK] REGISTRACE FONTŮ
        font_registered = False
        try:
            from reportlab.pdfbase.ttfonts import TTFont
            import os
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
        
        base_font = 'CzechFont' if font_registered else 'Helvetica'
        bold_font = 'CzechFont' if font_registered else 'Helvetica-Bold'

        # [OK] FUNKCE PRO VYTVOŘENÍ STORY (obsahu) - ROZŠÍŘENO
        def create_story():
            story = []
            
            # STYLY
            from reportlab.lib.styles import ParagraphStyle
            normal_style = ParagraphStyle('Normal', fontName=base_font, fontSize=9)
            bold_style = ParagraphStyle('Bold', fontName=bold_font, fontSize=9)
            small_style = ParagraphStyle('Small', fontName=base_font, fontSize=8)
            heading_style = ParagraphStyle('Heading', fontName=bold_font, fontSize=11)
            
            # HLAVIČKA
            cislo_data = [[f"Číslo {data['faktura'].cislo_faktury if data['faktura'] else '270325044'}"]]
            cislo_table = Table(cislo_data, colWidths=[500])
            cislo_table.setStyle(TableStyle([
                ('BOX', (0, 0), (-1, -1), 1, colors.black),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, -1), bold_font),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('TOPPADDING', (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ]))
            story.append(cislo_table)
            story.append(Spacer(1, 10))
            
            # Company info
            company_info = f"Dodavatel: {data['dodavatel'].nazev_sro_sro if data['dodavatel'] else 'Your energy, s.r.o.'}, " \
                          f"{data['dodavatel'].adresa_radek_1 if data['dodavatel'] else 'Italská 2584/69'}, " \
                          f"{data['dodavatel'].adresa_radek_2 if data['dodavatel'] else '120 00 Praha 2 - Vinohrady'}, " \
                          f"DIČ {data['dodavatel'].dic_sro if data['dodavatel'] else 'CZ24833851'} " \
                          f"IČO {data['dodavatel'].ico_sro if data['dodavatel'] else '24833851'}"
            
            story.append(Paragraph(company_info, normal_style))
            story.append(Spacer(1, 20))

            # PROCHÁZEJ ODBĚRNÁ MÍSTA
            from reportlab.platypus import KeepTogether
            
            for i, (vypocet, om) in enumerate(vypocty_om):
                # [OK] NAČTI CENY Z DATABÁZE
                from models import Odecet, CenaDodavatel, CenaDistribuce
                
                # Načti odečet
                odecet = Odecet.query.filter_by(
                    stredisko_id=stredisko_id,
                    obdobi_id=data['obdobi'].id,
                    oznaceni=om.cislo_om.zfill(7) if om.cislo_om else None
                ).first()
                
                # Načti ceny dodavatele z databáze
                ceny_dodavatel = CenaDodavatel.query.filter_by(
                    obdobi_id=data['obdobi'].id,
                    distribuce=data['stredisko'].distribuce,
                    sazba=om.distribucni_sazba_om,
                    jistic=om.kategorie_jistice_om
                ).first()
                
                # Načti ceny distribuce z databáze
                ceny_distribuce = CenaDistribuce.query.filter_by(
                    stredisko_id=stredisko_id,
                    rok=data['obdobi'].rok,
                    distribuce=data['stredisko'].distribuce,
                    sazba=om.distribucni_sazba_om,
                    jistic=om.kategorie_jistice_om
                ).first()
                
                # [OK] DYNAMICKÉ JEDNOTKOVÉ CENY Z DATABÁZE
                # Fallback hodnoty pokud nenajdeme ceny v DB
                cena_mesicni_plat = float(ceny_dodavatel.mesicni_plat) if ceny_dodavatel and ceny_dodavatel.mesicni_plat else 190.00
                cena_elektrinu_vt = float(ceny_dodavatel.platba_za_elektrinu_vt) if ceny_dodavatel and ceny_dodavatel.platba_za_elektrinu_vt else 3009.00
                cena_jistic = float(ceny_distribuce.platba_za_jistic) if ceny_distribuce and ceny_distribuce.platba_za_jistic else 575.00
                cena_distribuce_vt = float(ceny_distribuce.platba_za_distribuci_vt) if ceny_distribuce and ceny_distribuce.platba_za_distribuci_vt else 2460.33
                cena_systemove_sluzby = float(ceny_distribuce.systemove_sluzby) if ceny_distribuce and ceny_distribuce.systemove_sluzby else 170.92
                cena_poze = float(ceny_distribuce.poze_dle_spotreby) if ceny_distribuce and ceny_distribuce.poze_dle_spotreby else 495.00
                cena_nesitova = float(ceny_distribuce.nesitova_infrastruktura) if ceny_distribuce and ceny_distribuce.nesitova_infrastruktura else 8.45
                cena_dan = float(ceny_distribuce.dan_z_elektriny) if ceny_distribuce and ceny_distribuce.dan_z_elektriny else 28.30
                
                # Výpočty
                spotreba_vt_mwh = float(odecet.spotreba_vt or 0) / 1000 if odecet else 0.0
                spotreba_nt_mwh = float(odecet.spotreba_nt or 0) / 1000 if odecet else 0.0
                celkova_spotreba_mwh = spotreba_vt_mwh + spotreba_nt_mwh
                poze_minimum = min(float(vypocet.poze_dle_jistice or 0), float(vypocet.poze_dle_spotreby or 0))
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

                # VYTVOŘ OBSAH JEDNOHO OM
                om_content = []
                
                # Název OM
                om_title = f"Odběrné místo: {om.cislo_om} {om.nazev_om or ''}"
                om_content.append(Paragraph(f"<b>{om_title}</b>", bold_style))
                om_content.append(Spacer(1, 5))
                
                # Info o OM
                info_text = f"{data['stredisko'].adresa or ''} &nbsp;&nbsp;&nbsp;&nbsp; " \
                           f"Období fakturace: {data['faktura'].fakturace_od.strftime('%d.%m.%Y') if data['faktura'] and data['faktura'].fakturace_od else '01.03.2025'} " \
                           f"{data['faktura'].fakturace_do.strftime('%d.%m.%Y') if data['faktura'] and data['faktura'].fakturace_do else '31.03.2025'}"
                om_content.append(Paragraph(info_text, normal_style))
                
                info_text2 = f"Distribuční sazba: {om.distribucni_sazba_om or ''} &nbsp;&nbsp;&nbsp;&nbsp; " \
                            f"Kategorie hlavního jističe: {om.kategorie_jistice_om or ''} &nbsp;&nbsp;&nbsp;&nbsp; " \
                            f"Hodnota hlavního jističe [A]: {om.hodnota_jistice_om or ''}"
                om_content.append(Paragraph(info_text2, normal_style))
                om_content.append(Paragraph("EAN", normal_style))
                om_content.append(Spacer(1, 10))

                kategorie_jistice = om.kategorie_jistice_om or ''
                jistice_za_ampery = [
                    "nad 3x160A za každou 1A",
                    "nad 1x25A za každou 1A", 
                    "nad 3x63A za každou 1A"
                ]

                # Pokud je jistič "za každou 1A", použij hodnotu jističe jako množství
                if any(kategorie in kategorie_jistice for kategorie in jistice_za_ampery):
                    mnozstvi_staly_plat = om.hodnota_jistice_om or '1'
                    jednotka_staly_plat = 'A'  # ampéry
                else:
                    mnozstvi_staly_plat = '1'
                    jednotka_staly_plat = '1'  # kus

                # [OK] TABULKA S DYNAMICKÝMI CENAMI
                data_table = [
                    ['', 'Množství', 'MJ', 'Jednotková cena', 'Celková cena'],
                    ['Dodávka elektřiny', '', '', '', ''],
                    ['    Stálý plat', '1', '1', f"{cena_mesicni_plat:,.2f}".replace(',', ' '), f"{float(vypocet.mesicni_plat or 0):.2f}"],
                    ['    Plat za silovou elektřinu v VT', f"{spotreba_vt_mwh:.4f}", 'MWh', f"{cena_elektrinu_vt:,.2f}".replace(',', ' '), f"{float(vypocet.platba_za_elektrinu_vt or 0):.2f}"],
                    ['Distribuční služby', '', '', '', ''],
                    ['    Měsíční plat', mnozstvi_staly_plat, jednotka_staly_plat, f"{cena_jistic:,.2f}".replace(',', ' '), f"{float(vypocet.platba_za_jistic or 0):.2f}"],
                    ['    Plat za elektřinu ve VT', f"{spotreba_vt_mwh:.6f}", 'MWh', f"{cena_distribuce_vt:,.2f}".replace(',', ' '), f"{float(vypocet.platba_za_distribuci_vt or 0):.2f}"],
                    ['    Cena za systémové služby', f"{celkova_spotreba_mwh:.6f}", 'MWh', f"{cena_systemove_sluzby:.2f}", f"{float(vypocet.systemove_sluzby or 0):.2f}"],
                    ['    Podpora elekt. z podporovaných zdrojů energie', f"{celkova_spotreba_mwh:.6f}", 'MWh', f"{cena_poze:.2f}", f"{poze_minimum:.2f}"],
                    ['    Poplatek za nesíťovou infrastrukturu', '1', '1', f"{cena_nesitova:.2f}", f"{float(vypocet.nesitova_infrastruktura or 0):.2f}"],
                    ['Daň', '', '', '', ''],
                    ['    Daň', f"{celkova_spotreba_mwh:.4f}", 'MWh', f"{cena_dan:.2f}", f"{float(vypocet.dan_z_elektriny or 0):.2f}"],
                    ['Celkem', '', '', '', f"{celkem_om:.2f}"]
                ]

                table = Table(data_table, colWidths=[230, 50, 30, 80, 80])
                table.setStyle(TableStyle([
                    ('FONTSIZE', (0, 0), (-1, -1), 8),
                    ('FONTNAME', (0, 0), (-1, -1), base_font),
                    ('ALIGN', (1, 1), (-1, -1), 'RIGHT'),
                    ('ALIGN', (0, 0), (0, -1), 'LEFT'),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('LEFTPADDING', (0, 0), (-1, -1), 2),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 2),
                    ('TOPPADDING', (0, 0), (-1, -1), 1),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
                ]))

                om_content.append(table)
                story.append(KeepTogether(om_content))
                
                # Mezera mezi OM
                if i < len(vypocty_om) - 1:
                    story.append(Spacer(1, 15))
            
            # [OK] NOVÁ SEKCE - DŮLEŽITÉ INFORMACE
            from reportlab.platypus import PageBreak
            story.append(PageBreak())
            
            # Hlavní nadpis
            story.append(Paragraph("<b>Další důležité informace</b>", heading_style))
            story.append(Spacer(1, 15))
            
            # Energetická tabulka
            story.append(Paragraph("<b>Podíl jednotlivých zdrojů nebo původu energie na celkové směsi paliv dodavatele v roce 2024:</b>", bold_style))
            story.append(Spacer(1, 8))
            
            energy_data = [
                ['Původ elektřiny', '% podíl'],
                ['Uhelné elektrárny (uhlí)', '44,69'],
                ['Jaderné elektrárny (jádro)', '42,82'],
                ['Podíl elektřiny vyrobené ze zemního plynu', '5,79'],
                ['Obnovitelné zdroje energie (OZE)', '6,4'],
                ['Druhotné zdroje', '0,16'],
                ['Ostatní zdroje', '0,14'],
                ['celkem', '100']
            ]
            
            energy_table = Table(energy_data, colWidths=[350, 80])
            energy_table.setStyle(TableStyle([
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('FONTNAME', (0, 0), (-1, 0), bold_font),
                ('FONTNAME', (0, -1), (-1, -1), bold_font),  # Poslední řádek bold
                ('FONTNAME', (0, 1), (-1, -2), base_font),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
                ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
                ('ALIGN', (0, 0), (0, -1), 'LEFT'),
                ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))
            story.append(energy_table)
            story.append(Spacer(1, 15))
            
            # Informace o životním prostředí
            story.append(Paragraph("<b>Informace o dopadech výroby elektřiny na životní prostředí</b>", bold_style))
            story.append(Spacer(1, 5))
            story.append(Paragraph("Informace o dopadech výroby elektřiny na životní prostředí jsou dostupné na internetových stránkách Ministerstva životního prostředí www.mzp.cz.", small_style))
            story.append(Spacer(1, 12))
            
            # Reklamace
            story.append(Paragraph("<b>Reklamace, řešení sporů</b>", bold_style))
            story.append(Spacer(1, 5))
            
            # [OK] DYNAMICKÉ ÚDAJE Z DATABÁZE
            vystavovatel_email = vystavovatel.email_vystavitele if vystavovatel and vystavovatel.email_vystavitele else 'email@vystavovatel.cz'
            dodavatel_nazev = data['dodavatel'].nazev_sro_sro if data['dodavatel'] and data['dodavatel'].nazev_sro_sro else 'Your energy, s.r.o.'
            dodavatel_adresa1 = data['dodavatel'].adresa_radek_1 if data['dodavatel'] and data['dodavatel'].adresa_radek_1 else 'Italská 2584/69'
            dodavatel_adresa2 = data['dodavatel'].adresa_radek_2 if data['dodavatel'] and data['dodavatel'].adresa_radek_2 else '120 00 Praha 2 - Vinohrady'
            
            reklamace_text = f"Zákazník může k vyúčtování dodávek elektřiny a souvisejících služeb uplatnit reklamaci na adrese <b>{vystavovatel_email}</b> nebo na adrese <b>{dodavatel_nazev}, {dodavatel_adresa1} {dodavatel_adresa2}</b>, ve lhůtě do 30 dnů ode dne doručení. V případě vzniku sporu mezi zákazníkem a dodavatelem může zákazník podat návrh na rozhodnutí tohoto sporu podle § 17 odst. 7 energetického zákona, přitom musí postupovat podle správního řádu."
            story.append(Paragraph(reklamace_text, small_style))
            story.append(Spacer(1, 12))
            
            # Změna dodavatele
            story.append(Paragraph("<b>Změna dodavatele</b>", bold_style))
            story.append(Spacer(1, 5))
            zmena_text = "Zákazníci a spotřebitelé mají právo zvolit si a bezplatně změnit svého dodavatele. Každý zákazník se podpisem smlouvy zavázal dodržet její podmínky. Pokud je smlouva uzavřena na dobu určitou, je zákazník povinen tento závazek dodržet. Při ukončení smluvního vztahu je tedy nutné postupovat dle smlouvy, dodatku a všeobecných obchodních podmínek, které jsou nedílnou součástí každé smlouvy. Před změnou dodavatele je vhodné si zjistit, zda je změna dodavatele výhodná, a to nejen srovnáním ceny, ale i Obchodních podmínek dodavatele. Pro nezávislé porovnání cenových nabídek dodavatelů můžete využít například kalkulačku Energetického regulačního úřadu, kterou naleznete na adrese www.eru.cz"
            story.append(Paragraph(zmena_text, small_style))
            story.append(Spacer(1, 15))
            
            # Kontaktní údaje
            story.append(Paragraph("<b>Důležité kontaktní údaje</b>", bold_style))
            story.append(Spacer(1, 10))
            
            # ERÚ
            story.append(Paragraph("<b>Energetický regulační úřad</b>", bold_style))
            story.append(Spacer(1, 5))
            
            eru_data = [
                ['adresa sídla', 'Masarykovo náměstí 5, 586 01 Jihlava'],
                ['telefonní číslo', '564 578 666 - ústředna'],
                ['adresa webových stránek', 'www.eru.cz'],
                ['adresa elektronické podatelny', 'podatelna@eru.cz']
            ]
            
            eru_table = Table(eru_data, colWidths=[120, 300])
            eru_table.setStyle(TableStyle([
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('FONTNAME', (0, 0), (0, -1), bold_font),
                ('FONTNAME', (1, 0), (1, -1), base_font),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
                ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))
            story.append(eru_table)
            story.append(Spacer(1, 10))
            
            # MPO
            story.append(Paragraph("<b>Ministerstvo průmyslu a obchodu</b>", bold_style))
            story.append(Spacer(1, 5))
            
            mpo_data = [
                ['adresa sídla', 'Na Františku 32, 110 15 Praha 1'],
                ['telefonní číslo', '224 851 111'],
                ['adresa webových stránek', 'www.mpo.cz'],
                ['adresa elektronické podatelny', 'posta@mpo.cz']
            ]
            
            mpo_table = Table(mpo_data, colWidths=[120, 300])
            mpo_table.setStyle(TableStyle([
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('FONTNAME', (0, 0), (0, -1), bold_font),
                ('FONTNAME', (1, 0), (1, -1), base_font),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
                ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))
            story.append(mpo_table)
            
            return story

        # [OK] 1. PRŮCHOD - zjistíme počet stránek
        temp_buffer = io.BytesIO()
        temp_doc = SimpleDocTemplate(temp_buffer, pagesize=A4)
        temp_story = create_story()
        temp_doc.build(temp_story)
        
        # Vypočítáme počet stránek z velikosti temp dokumentu
        temp_buffer.seek(0)
        try:
            reader = create_pdf_reader(temp_buffer)
            total_pages = len(reader.pages)
        except:
            # Fallback - odhad počtu stránek
            total_pages = max(1, len(vypocty_om) // 2 + 2)  # +2 pro důležité informace
        
        # [OK] 2. PRŮCHOD - vytvoříme finální PDF se stránkováním
        buffer = io.BytesIO()
        
        # Globální proměnná pro počet stránek
        TOTAL_PAGES = total_pages
        
        # Custom template s footer funkcí
        def add_page_number(canvas, doc):
            """Přidá stránkování do footeru"""
            canvas.saveState()
            canvas.setFont('CzechFont' if font_registered else 'Helvetica', 9)
            page_num = f"Strana {doc.page} z {TOTAL_PAGES}"
            # Vycentrovat na spodu stránky
            text_width = canvas.stringWidth(page_num, 'CzechFont' if font_registered else 'Helvetica', 9)
            x = (A4[0] - text_width) / 2
            canvas.drawString(x, 15*mm, page_num)
            canvas.restoreState()
        
        # Vytvoř finální dokument
        from reportlab.platypus import BaseDocTemplate, PageTemplate, Frame
        doc = BaseDocTemplate(buffer, pagesize=A4, 
                            rightMargin=20*mm, leftMargin=20*mm,
                            topMargin=20*mm, bottomMargin=30*mm)
        
        frame = Frame(20*mm, 30*mm, A4[0]-40*mm, A4[1]-50*mm, id='normal')
        template = PageTemplate(id='later', frames=frame, onPage=add_page_number)
        doc.addPageTemplates([template])
        
        # Vytvoř story znovu
        final_story = create_story()
        doc.build(final_story)
        
        pdf = buffer.getvalue()
        buffer.close()
        temp_buffer.close()
        
        response = make_response(pdf)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'inline; filename=priloha2_{rok}_{mesic:02d}.pdf'
        
        return response

    except Exception as e:
        error_msg = str(e)
        if 'PDF.__init__()' in error_msg or 'PyPDF2' in error_msg or 'positional argument' in error_msg:
            flash(f"[WARNING] Príloha 2 nie je dostupná kvôli problémom s PDF knižnicou na serveri. Skúste použiť kompletný PDF súbor.")
        else:
            flash(f"[ERROR] Chyba při generování PDF: {error_msg}")
        return redirect(url_for('fakturace.fakturace', stredisko_id=stredisko_id))    

@print_bp.route("/<int:stredisko_id>/<int:rok>-<int:mesic>/kompletni/pdf")
def vygenerovat_kompletni_pdf(stredisko_id, rok, mesic):
    """Generuje kompletní PDF - faktura + příloha 1 + příloha 2 v jednom souboru"""
    if not session.get("user_id"):
        return redirect("/login")

    stredisko = Stredisko.query.get_or_404(stredisko_id)
    if stredisko.user_id != session["user_id"]:
        return "Nepovolený přístup", 403

    try:
        import io
        from flask import url_for
        
        # Vytvoř PdfWriter pro spojení
        merger = PdfWriter()
        
        # 1. ZÍSKEJ PDF FAKTURU
        try:
            # Zavolej pomocnou funkci pro získání PDF bytes
            faktura_bytes = _get_faktura_pdf_bytes(stredisko_id, rok, mesic)
            faktura_pdf = create_pdf_reader(io.BytesIO(faktura_bytes))
            for page in faktura_pdf.pages:
                add_page_to_writer(merger, page)
            print(f"[OK] Přidána faktura - {len(faktura_pdf.pages)} stránek")
        except Exception as e:
            print(f"[ERROR] Chyba při generování faktury: {e}")
            return f"Chyba při generování faktury: {e}", 500
        
        # 2. ZÍSKEJ PDF PŘÍLOHU 1
        try:
            priloha1_response = vygenerovat_prilohu1_pdf(stredisko_id, rok, mesic)
            if hasattr(priloha1_response, 'data'):
                priloha1_pdf = create_pdf_reader(io.BytesIO(priloha1_response.data))
                for page in priloha1_pdf.pages:
                    add_page_to_writer(merger, page)
                print(f"[OK] Přidána příloha 1 - {len(priloha1_pdf.pages)} stránek")
        except Exception as e:
            print(f"[ERROR] Chyba při generování přílohy 1: {e}")
            return f"Chyba při generování přílohy 1: {e}", 500
        
        # 3. ZÍSKEJ PDF PŘÍLOHU 2 (ReportLab verze)
        try:
            # Použij novou ReportLab funkci místo WeasyPrint
            priloha2_response = priloha2_pdf_nova(stredisko_id, rok, mesic)
            if hasattr(priloha2_response, 'data'):
                priloha2_pdf = create_pdf_reader(io.BytesIO(priloha2_response.data))
                for page in priloha2_pdf.pages:
                    add_page_to_writer(merger, page)
                print(f"[OK] Přidána příloha 2 (ReportLab) - {len(priloha2_pdf.pages)} stránek")
        except Exception as e:
            print(f"[ERROR] Chyba při generování přílohy 2: {e}")
            return f"Chyba při generování přílohy 2: {e}", 500
        
        # 4. VYTVOŘ FINÁLNÍ PDF
        output_buffer = io.BytesIO()
        write_pdf_to_stream(merger, output_buffer)
        close_pdf_writer(merger)
        
        pdf_data = output_buffer.getvalue()
        output_buffer.close()
        
        # 5. VRAŤ ODPOVĚĎ
        response = make_response(pdf_data)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'inline; filename=kompletni_faktura_{rok}_{mesic:02d}.pdf'
        
        flash(f"[OK] Kompletní PDF bylo úspěšně vygenerováno")
        return response
        
    except Exception as e:
        flash(f"[ERROR] Chyba při generování kompletního PDF: {str(e)}")
        return redirect(url_for('fakturace.fakturace', stredisko_id=stredisko_id))
