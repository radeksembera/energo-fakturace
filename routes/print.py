from flask import Blueprint, render_template, render_template_string, request, redirect, url_for, session, flash, make_response
from models import db, Stredisko, Faktura, ZalohovaFaktura, InfoDodavatele, InfoOdberatele, InfoVystavovatele, VypocetOM, OdberneMisto, Odečet, ObdobiFakturace
# Alias pro zpětnou kompatibilitu s kódem bez diakritiky
Odecet = Odečet
from datetime import datetime
import io

# ✅ REPORTLAB IMPORTS
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
from PyPDF2 import PdfReader 

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
    
    # Načti výpočty
    vypocty = VypocetOM.query.filter(VypocetOM.id > 0)\
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
        'dofakturace_bonus': dofakturace_bonus,  # ✅ DOFAKTURACE/BONUS
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
        
        # ✅ ROZŠÍŘENÝ SEZNAM FONTŮ S ČESKOU PODPOROU
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
                    # ✅ REGISTRUJ ZÁKLADNÍ A TUČNÝ FONT
                    pdfmetrics.registerFont(TTFont('CzechFont', font_path))
                    
                    # Pokud existuje bold verze, registruj i tu
                    bold_path = font_path.replace('.ttf', 'b.ttf').replace('.ttf', 'bd.ttf')
                    if os.path.exists(bold_path):
                        pdfmetrics.registerFont(TTFont('CzechFont-Bold', bold_path))
                    
                    print(f"✅ Registrován český font: {font_path}")
                    font_registered = True
                    break
                except Exception as e:
                    print(f"⚠️ Chyba při registraci fontu {font_path}: {e}")
                    continue
        
        # ✅ FALLBACK - DejaVu Sans má perfektní českou podporu
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
                print("✅ Stažen a registrován DejaVu Sans font")
                
            except Exception as e:
                print(f"⚠️ Nepodařilo se stáhnout DejaVu font: {e}")
        
        return font_registered
        
    except Exception as e:
        print(f"❌ Chyba při registraci fontů: {e}")
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

@print_bp.route("/<int:stredisko_id>/<int:rok>-<int:mesic>/faktura/pdf")
def vygenerovat_fakturu_pdf(stredisko_id, rok, mesic):
    """Generuje PDF fakturu identickou s HTML verzí"""
    data, error = get_faktura_data(stredisko_id, rok, mesic)
    if error:
        return error
    
    try:
        buffer = io.BytesIO()
        
        # ✅ STEJNÉ NASTAVENÍ JAKO PŮVODNĚ
        doc = SimpleDocTemplate(buffer, pagesize=A4, 
                              rightMargin=20*mm, leftMargin=20*mm,
                              topMargin=20*mm, bottomMargin=20*mm)
        
        story = []
        styles = getSampleStyleSheet()
        font_registered = False
        
        # ✅ STEJNÁ REGISTRACE FONTŮ JAKO PŮVODNĚ
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
            
            if font_registered:
                styles['Normal'].fontName = 'CzechFont'
                styles['Heading1'].fontName = 'CzechFont'
                styles['Heading2'].fontName = 'CzechFont'
                styles['Title'].fontName = 'CzechFont'
        except:
            pass
        
        # ✅ HLAVIČKA - STEJNÁ STRUKTURA, JINÝ DESIGN
        hlavicka_data = [
            [
                # Levá strana - dodavatel
                [
                    Paragraph("<b>FAKTURA - DAŇOVÝ DOKLAD</b>", styles['Heading1']),
                    Paragraph(f"<b>{data['dodavatel'].nazev_sro if data['dodavatel'] else 'Your energy, s.r.o.'}</b>", styles['Normal']),
                    Paragraph(f"{data['dodavatel'].adresa_radek_1 if data['dodavatel'] else 'Italská 2584/69'}", styles['Normal']),
                    Paragraph(f"{data['dodavatel'].adresa_radek_2 if data['dodavatel'] else '120 00 Praha 2 - Vinohrady'}", styles['Normal']),
                    Paragraph(f"<b>DIČ</b> {data['dodavatel'].dic_sro if data['dodavatel'] else 'CZ24833851'}", styles['Normal']),
                    Paragraph(f"<b>IČO</b> {data['dodavatel'].ico_sro if data['dodavatel'] else '24833851'}", styles['Normal']),
                    Paragraph("", styles['Normal']),
                    Paragraph(f"<b>Banka:</b> {data['dodavatel'].banka if data['dodavatel'] else 'Bankovní účet Raiffeisenbank a.s. CZK'}", styles['Normal']),
                    Paragraph(f"<b>Č.úč.</b> {data['dodavatel'].cislo_uctu if data['dodavatel'] else '5041011366/5500'}", styles['Normal']),
                    Paragraph(f"<b>IBAN</b> {data['dodavatel'].iban if data['dodavatel'] else 'CZ1055000000005041011366'}", styles['Normal']),
                    Paragraph(f"<b>SWIFT/BIC</b> {data['dodavatel'].swift if data['dodavatel'] else 'RZBCCZPP'}", styles['Normal']),
                ],
                # Pravá strana - faktura info + odběratel
                [
                    Paragraph(f"<b>Číslo {data['faktura'].cislo_faktury if data['faktura'] else ''}</b>", styles['Heading2']),
                    Paragraph("", styles['Normal']),
                    Paragraph(f"<b>konst. symbol</b> {data['faktura'].konstantni_symbol if data['faktura'] else ''}", styles['Normal']),
                    Paragraph(f"<b>VS</b> {data['faktura'].variabilni_symbol if data['faktura'] else ''}", styles['Normal']),
                    Paragraph("", styles['Normal']),
                    Paragraph("Objednávka:", styles['Normal']),
                    Paragraph("", styles['Normal']),
                    # Odběratel box
                    Paragraph("<b>Odběratel:</b>", styles['Normal']),
                    Paragraph(f"<b>{data['odberatel'].nazev_sro if data['odberatel'] else ''}</b>", styles['Normal']),
                    Paragraph(f"{data['odberatel'].adresa_radek_1 if data['odberatel'] else ''}", styles['Normal']),
                    Paragraph(f"{data['odberatel'].adresa_radek_2 if data['odberatel'] else ''}", styles['Normal']),
                    Paragraph(f"<b>IČO:</b> {data['odberatel'].ico_sro if data['odberatel'] else ''}", styles['Normal']),
                    Paragraph(f"<b>DIČ:</b> {data['odberatel'].dic_sro if data['odberatel'] else ''}", styles['Normal']),
                    Paragraph("", styles['Normal']),
                    Paragraph(f"<b>Středisko:</b> {data['stredisko'].stredisko} {data['stredisko'].nazev_strediska}", styles['Normal']),
                    Paragraph(f"{data['stredisko'].stredisko_mail if data['stredisko'].stredisko_mail else 'info@yourenergy.cz'}", styles['Normal']),
                ]
            ]
        ]
        
        hlavicka_table = Table(hlavicka_data, colWidths=[250, 250])
        hlavicka_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('FONTNAME', (0, 0), (-1, -1), 'CzechFont' if font_registered else 'Helvetica'),
            # ✅ PŘIDÁME RÁMEČEK KOLEM ODBĚRATELE
            ('BOX', (1, 0), (1, 0), 1, colors.black),
            ('LEFTPADDING', (1, 0), (1, 0), 8),
            ('RIGHTPADDING', (1, 0), (1, 0), 8),
            ('TOPPADDING', (1, 0), (1, 0), 8),
            ('BOTTOMPADDING', (1, 0), (1, 0), 8),
        ]))
        
        story.append(hlavicka_table)
        story.append(Spacer(1, 20))
        
        # ✅ PODMÍNKY - BEZ BAREV, POUZE ČÁRY
        podmínky_data = [
            ['Dodací a platební podmínky', '', ''],
            ['Datum splatnosti', 'Datum vystavení', 'Datum zdanit. plnění'],
            [
                data['faktura'].datum_splatnosti.strftime('%d.%m.%Y') if data['faktura'] and data['faktura'].datum_splatnosti else '',
                data['faktura'].datum_vystaveni.strftime('%d.%m.%Y') if data['faktura'] and data['faktura'].datum_vystaveni else '',
                data['faktura'].datum_zdanitelneho_plneni.strftime('%d.%m.%Y') if data['faktura'] and data['faktura'].datum_zdanitelneho_plneni else ''
            ],
            ['Forma úhrady', 'Popis dodávky', ''],
            [
                data['faktura'].forma_uhrady if data['faktura'] else '',
                data['faktura'].popis_dodavky if data['faktura'] else f"Vyúčtování {data['obdobi'].rok}{data['obdobi'].mesic:02d}",
                ''
            ]
        ]
        
        podmínky_table = Table(podmínky_data, colWidths=[150, 150, 150])
        podmínky_table.setStyle(TableStyle([
            # ✅ BEZ BAREV - POUZE ČÁRY A BOLD
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('FONTNAME', (0, 0), (-1, 0), 'CzechFont' if font_registered else 'Helvetica-Bold'),  # První řádek bold
            ('FONTNAME', (0, 1), (-1, 1), 'CzechFont' if font_registered else 'Helvetica-Bold'),  # Druhý řádek bold
            ('FONTNAME', (0, 3), (-1, 3), 'CzechFont' if font_registered else 'Helvetica-Bold'),  # Čtvrtý řádek bold
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTNAME', (0, 2), (-1, 2), 'CzechFont' if font_registered else 'Helvetica'),  # Data normální
            ('FONTNAME', (0, 4), (-1, 4), 'CzechFont' if font_registered else 'Helvetica'),  # Data normální
        ]))
        
        story.append(podmínky_table)
        story.append(Spacer(1, 15))
        
        # ✅ REKAPITULACE - BEZ BAREV
        rekapitulace = data['rekapitulace']
        sazba_dph = data['sazba_dph']
        sazba_dph_procenta = int(sazba_dph * 100)
        
        rekapitulace_data = [
            ['Rekapitulace', 'Základ daně', 'Sazba DPH', 'Částka DPH', 'Celkem vč. DPH'],
            ['Měsíční plat (za jistič)', f"{rekapitulace['platba_za_jistic']:.2f}", f"{sazba_dph_procenta}", f"{rekapitulace['platba_za_jistic'] * sazba_dph:.2f}", f"{rekapitulace['platba_za_jistic'] * (1 + sazba_dph):.2f}"],
            ['Plat za elektřinu ve VT', f"{rekapitulace['distribuce_vt']:.2f}", f"{sazba_dph_procenta}", f"{rekapitulace['distribuce_vt'] * sazba_dph:.2f}", f"{rekapitulace['distribuce_vt'] * (1 + sazba_dph):.2f}"],
            ['Plat za elektřinu ve NT', f"{rekapitulace['distribuce_nt']:.2f}", f"{sazba_dph_procenta}", f"{rekapitulace['distribuce_nt'] * sazba_dph:.2f}", f"{rekapitulace['distribuce_nt'] * (1 + sazba_dph):.2f}"],
            ['Cena za systémové služby', f"{rekapitulace['systemove_sluzby']:.2f}", f"{sazba_dph_procenta}", f"{rekapitulace['systemove_sluzby'] * sazba_dph:.2f}", f"{rekapitulace['systemove_sluzby'] * (1 + sazba_dph):.2f}"],
            ['Podpora elekt. z podporovaných zdrojů energie', f"{rekapitulace['poze_minimum']:.2f}", f"{sazba_dph_procenta}", f"{rekapitulace['poze_minimum'] * sazba_dph:.2f}", f"{rekapitulace['poze_minimum'] * (1 + sazba_dph):.2f}"],
            ['Poplatek za nesíťovou infrastrukturu', f"{rekapitulace['nesitova_infrastruktura']:.2f}", f"{sazba_dph_procenta}", f"{rekapitulace['nesitova_infrastruktura'] * sazba_dph:.2f}", f"{rekapitulace['nesitova_infrastruktura'] * (1 + sazba_dph):.2f}"],
            ['Stálý plat (dodavatel)', f"{rekapitulace['mesicni_plat']:.2f}", f"{sazba_dph_procenta}", f"{rekapitulace['mesicni_plat'] * sazba_dph:.2f}", f"{rekapitulace['mesicni_plat'] * (1 + sazba_dph):.2f}"],
            ['Plat za silovou elektřinu v VT (dodavatel)', f"{rekapitulace['elektrinu_vt']:.2f}", f"{sazba_dph_procenta}", f"{rekapitulace['elektrinu_vt'] * sazba_dph:.2f}", f"{rekapitulace['elektrinu_vt'] * (1 + sazba_dph):.2f}"],
            ['Plat za silovou elektřinu v NT (dodavatel)', f"{rekapitulace['elektrinu_nt']:.2f}", f"{sazba_dph_procenta}", f"{rekapitulace['elektrinu_nt'] * sazba_dph:.2f}", f"{rekapitulace['elektrinu_nt'] * (1 + sazba_dph):.2f}"],
            ['Daň', f"{rekapitulace['dan_z_elektriny']:.2f}", f"{sazba_dph_procenta}", f"{rekapitulace['dan_z_elektriny'] * sazba_dph:.2f}", f"{rekapitulace['dan_z_elektriny'] * (1 + sazba_dph):.2f}"],
            ['Dofakturace / Bonus', f"{rekapitulace['dofakturace_bonus']:.2f}", f"{sazba_dph_procenta}", f"{rekapitulace['dofakturace_bonus'] * sazba_dph:.2f}", f"{rekapitulace['dofakturace_bonus'] * (1 + sazba_dph):.2f}"],
            ['CELKEM ZA DOKLAD', f"{data['zaklad_bez_dph']:.2f}", '', f"{data['castka_dph']:.2f}", f"{data['celkem_vc_dph']:.2f}"],
            ['Zaplaceno zálohou', f"{-data['zaloha_hodnota']:.2f}", f"{sazba_dph_procenta}", f"{-data['zaloha_dph']:.2f}", f"{-data['zaloha_celkem_vc_dph']:.2f}"],
        ]
        
        rekapitulace_table = Table(rekapitulace_data, colWidths=[180, 80, 60, 80, 80])
        rekapitulace_table.setStyle(TableStyle([
            # ✅ BEZ BAREV - POUZE ČÁRY A BOLD
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('FONTNAME', (0, 0), (-1, 0), 'CzechFont' if font_registered else 'Helvetica-Bold'),  # Hlavička bold
            ('FONTNAME', (0, 12), (-1, 12), 'CzechFont' if font_registered else 'Helvetica-Bold'),  # CELKEM bold
            ('ALIGN', (1, 1), (-1, -1), 'RIGHT'),  # Čísla vpravo
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),   # Názvy vlevo
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTNAME', (0, 1), (-1, 11), 'CzechFont' if font_registered else 'Helvetica'),  # Data normální
            ('FONTNAME', (0, 13), (-1, 13), 'CzechFont' if font_registered else 'Helvetica'),  # Záloha normální
        ]))
        
        story.append(rekapitulace_table)
        story.append(Spacer(1, 20))
        
        # ✅ K PLATBĚ
        story.append(Paragraph(f"<b>K platbě celkem Kč {data['k_platbe']:.2f}</b>", styles['Title']))
        story.append(Spacer(1, 15))
        
        # ✅ REKAPITULACE DPH - BEZ BAREV
        dph_data = [
            ['Rekapitulace DPH', '', '', ''],
            ['Sazba DPH', 'Základ daně', 'DPH', 'Celkem'],
            ['Základní sazba 21 %', f"{data['k_platbe'] / (1 + sazba_dph):.2f}", f"{data['k_platbe'] * sazba_dph / (1 + sazba_dph):.2f}", f"{data['k_platbe']:.2f}"],
        ]
        
        dph_table = Table(dph_data, colWidths=[120, 80, 80, 80])
        dph_table.setStyle(TableStyle([
            # ✅ BEZ BAREV
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('FONTNAME', (0, 0), (-1, 0), 'CzechFont' if font_registered else 'Helvetica-Bold'),
            ('FONTNAME', (0, 1), (-1, 1), 'CzechFont' if font_registered else 'Helvetica-Bold'),
            ('ALIGN', (1, 1), (-1, -1), 'RIGHT'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTNAME', (0, 2), (-1, 2), 'CzechFont' if font_registered else 'Helvetica'),
        ]))
        
        story.append(dph_table)
        story.append(Spacer(1, 20))
        
        # ✅ FOOTER
        story.append(Paragraph("Rozpis jednotlivých položek faktury je uveden na následující straně.", styles['Normal']))
        story.append(Paragraph(f"<b>FAKTURA:</b> {data['faktura'].cislo_faktury if data['faktura'] else '270325044'} &nbsp;&nbsp;&nbsp;&nbsp; Strana: 1 / 22", styles['Normal']))
        
        # ✅ GENERUJ PDF
        doc.build(story)
        
        pdf = buffer.getvalue()
        buffer.close()
        
        response = make_response(pdf)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'inline; filename=faktura_{rok}_{mesic:02d}.pdf'
        
        return response
        
    except Exception as e:
        flash(f"❌ Chyba při generování PDF: {str(e)}")
        return redirect(url_for('fakturace.fakturace', stredisko_id=stredisko_id))
    

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
        
        # ✅ REGISTRUJ ČESKÉ FONTY
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
        
        # ✅ HLAVIČKA - STEJNÁ JAKO HTML
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
        
        # ✅ DODACÍ A PLATEBNÍ PODMÍNKY
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
        
        # ✅ ZÁLOHOVÁ ČÁSTKA
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
        
        # ✅ VYSTAVOVATEL
        if vystavovatel:
            story.append(Paragraph(f"<b>Vystavil:</b> {vystavovatel.jmeno_vystavitele if vystavovatel.jmeno_vystavitele else ''}", styles['Normal']))
            story.append(Paragraph(f"<b>Telefon:</b> {vystavovatel.telefon_vystavitele if vystavovatel.telefon_vystavitele else ''}", styles['Normal']))
            story.append(Paragraph(f"<b>Email:</b> {vystavovatel.email_vystavitele if vystavovatel.email_vystavitele else ''}", styles['Normal']))
        
        # ✅ GENERUJ PDF
        doc.build(story)
        
        pdf = buffer.getvalue()
        buffer.close()
        
        response = make_response(pdf)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'inline; filename=zalohova_{rok}_{mesic:02d}.pdf'
        
        return response
        
    except Exception as e:
        flash(f"❌ Chyba při generování PDF: {str(e)}")
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
    
    # Načti pouze odečty s existujícími odběrnými místy - INNER JOIN
    odecty = db.session.query(Odecet, OdberneMisto)\
        .join(OdberneMisto, (Odecet.oznaceni == OdberneMisto.cislo_om) & (OdberneMisto.stredisko_id == stredisko_id))\
        .filter(Odecet.stredisko_id == stredisko_id)\
        .filter(Odecet.obdobi_id == obdobi.id)\
        .order_by(Odecet.oznaceni)\
        .all()
    
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
        
        # Načti pouze odečty s existujícími odběrnými místy - INNER JOIN
        odecty = db.session.query(Odecet, OdberneMisto)\
            .join(OdberneMisto, (Odecet.oznaceni == OdberneMisto.cislo_om) & (OdberneMisto.stredisko_id == stredisko_id))\
            .filter(Odecet.stredisko_id == stredisko_id)\
            .filter(Odecet.obdobi_id == obdobi.id)\
            .order_by(Odecet.oznaceni)\
            .all()

        # ✅ REGISTRACE FONTŮ
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

        # ✅ FUNKCE PRO VYTVOŘENÍ STORY (obsahu)
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

        # ✅ 1. PRŮCHOD - zjistíme počet stránek
        temp_buffer = io.BytesIO()
        temp_doc = SimpleDocTemplate(temp_buffer, pagesize=A4, 
                                  rightMargin=15*mm, leftMargin=15*mm,
                                  topMargin=20*mm, bottomMargin=20*mm)
        temp_story = create_story()
        temp_doc.build(temp_story)
        
        # Vypočítáme počet stránek
        temp_buffer.seek(0)
        from PyPDF2 import PdfReader
        try:
            reader = PdfReader(temp_buffer)
            total_pages = len(reader.pages)
        except:
            # Fallback - odhad počtu stránek
            total_pages = max(1, len(odecty) // 3)  # Odhad: 3 OM na stránku
        
        # ✅ 2. PRŮCHOD - vytvoříme finální PDF se stránkováním
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
        flash(f"❌ Chyba při generování PDF: {str(e)}")
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
        
        vypocty_data.append({
            'om': om,
            'vypocet': vypocet,
            'odecet': odecet,
            'poze_minimum': poze_minimum,
            'celkem_om': celkem_om,
            'sazba_dph': sazba_dph
        })

    # ✅ OPRAVA: Renderuj template s UTF-8 kódováním
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


@print_bp.route("/<int:stredisko_id>/<int:rok>-<int:mesic>/priloha2/pdf")
def vygenerovat_prilohu2_pdf(stredisko_id, rok, mesic):
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

        # ✅ REGISTRACE FONTŮ
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

        # ✅ FUNKCE PRO VYTVOŘENÍ STORY (obsahu) - ROZŠÍŘENO
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
            company_info = f"Dodavatel: {data['dodavatel'].nazev_sro if data['dodavatel'] else 'Your energy, s.r.o.'}, " \
                          f"{data['dodavatel'].adresa_radek_1 if data['dodavatel'] else 'Italská 2584/69'}, " \
                          f"{data['dodavatel'].adresa_radek_2 if data['dodavatel'] else '120 00 Praha 2 - Vinohrady'}, " \
                          f"DIČ {data['dodavatel'].dic_sro if data['dodavatel'] else 'CZ24833851'} " \
                          f"IČO {data['dodavatel'].ico_sro if data['dodavatel'] else '24833851'}"
            
            story.append(Paragraph(company_info, normal_style))
            story.append(Spacer(1, 20))

            # PROCHÁZEJ ODBĚRNÁ MÍSTA
            from reportlab.platypus import KeepTogether
            
            for i, (vypocet, om) in enumerate(vypocty_om):
                # ✅ NAČTI CENY Z DATABÁZE
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
                
                # ✅ DYNAMICKÉ JEDNOTKOVÉ CENY Z DATABÁZE
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

                # ✅ TABULKA S DYNAMICKÝMI CENAMI
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
            
            # ✅ NOVÁ SEKCE - DŮLEŽITÉ INFORMACE
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
            
            # ✅ DYNAMICKÉ ÚDAJE Z DATABÁZE
            vystavovatel_email = vystavovatel.email_vystavitele if vystavovatel and vystavovatel.email_vystavitele else 'email@vystavovatel.cz'
            dodavatel_nazev = data['dodavatel'].nazev_sro if data['dodavatel'] and data['dodavatel'].nazev_sro else 'Your energy, s.r.o.'
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

        # ✅ 1. PRŮCHOD - zjistíme počet stránek
        temp_buffer = io.BytesIO()
        temp_doc = SimpleDocTemplate(temp_buffer, pagesize=A4)
        temp_story = create_story()
        temp_doc.build(temp_story)
        
        # Vypočítáme počet stránek z velikosti temp dokumentu
        temp_buffer.seek(0)
        try:
            reader = PdfReader(temp_buffer)
            total_pages = len(reader.pages)
        except:
            # Fallback - odhad počtu stránek
            total_pages = max(1, len(vypocty_om) // 2 + 2)  # +2 pro důležité informace
        
        # ✅ 2. PRŮCHOD - vytvoříme finální PDF se stránkováním
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
        flash(f"❌ Chyba při generování PDF: {str(e)}")
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
        from PyPDF2 import PdfWriter, PdfReader
        import io
        from flask import url_for
        
        # Vytvoř PdfWriter pro spojení
        merger = PdfWriter()
        
        # 1. ZÍSKEJ PDF FAKTURU
        try:
            # Zavolej interně funkci pro generování faktury
            faktura_response = vygenerovat_fakturu_pdf(stredisko_id, rok, mesic)
            if hasattr(faktura_response, 'data'):
                faktura_pdf = PdfReader(io.BytesIO(faktura_response.data))
                for page in faktura_pdf.pages:
                    merger.add_page(page)
                print(f"✅ Přidána faktura - {len(faktura_pdf.pages)} stránek")
        except Exception as e:
            print(f"❌ Chyba při generování faktury: {e}")
            return f"Chyba při generování faktury: {e}", 500
        
        # 2. ZÍSKEJ PDF PŘÍLOHU 1
        try:
            priloha1_response = vygenerovat_prilohu1_pdf(stredisko_id, rok, mesic)
            if hasattr(priloha1_response, 'data'):
                priloha1_pdf = PdfReader(io.BytesIO(priloha1_response.data))
                for page in priloha1_pdf.pages:
                    merger.add_page(page)
                print(f"✅ Přidána příloha 1 - {len(priloha1_pdf.pages)} stránek")
        except Exception as e:
            print(f"❌ Chyba při generování přílohy 1: {e}")
            return f"Chyba při generování přílohy 1: {e}", 500
        
        # 3. ZÍSKEJ PDF PŘÍLOHU 2
        try:
            priloha2_response = vygenerovat_prilohu2_pdf(stredisko_id, rok, mesic)
            if hasattr(priloha2_response, 'data'):
                priloha2_pdf = PdfReader(io.BytesIO(priloha2_response.data))
                for page in priloha2_pdf.pages:
                    merger.add_page(page)
                print(f"✅ Přidána příloha 2 - {len(priloha2_pdf.pages)} stránek")
        except Exception as e:
            print(f"❌ Chyba při generování přílohy 2: {e}")
            return f"Chyba při generování přílohy 2: {e}", 500
        
        # 4. VYTVOŘ FINÁLNÍ PDF
        output_buffer = io.BytesIO()
        merger.write(output_buffer)
        merger.close()
        
        pdf_data = output_buffer.getvalue()
        output_buffer.close()
        
        # 5. VRAŤ ODPOVĚĎ
        response = make_response(pdf_data)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'inline; filename=kompletni_faktura_{rok}_{mesic:02d}.pdf'
        
        flash(f"✅ Kompletní PDF bylo úspěšně vygenerováno")
        return response
        
    except Exception as e:
        flash(f"❌ Chyba při generování kompletního PDF: {str(e)}")
        return redirect(url_for('fakturace.fakturace', stredisko_id=stredisko_id))
