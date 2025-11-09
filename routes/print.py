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


# ============== HTML FAKTURA ==============

@print_bp.route("/<int:stredisko_id>/<int:rok>-<int:mesic>/faktura/html")
def vygenerovat_fakturu_html(stredisko_id, rok, mesic):
    """Generuje HTML fakturu"""
    data, error = get_faktura_data(stredisko_id, rok, mesic)
    if error:
        return error
    
    return render_template("print/faktura.html", **data)

# ============== PDF FAKTURA ==============


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
        poze_jistic = float(vypocet.poze_dle_jistice or 0)
        poze_spotreba = float(vypocet.poze_dle_spotreby or 0)
        poze_minimum = min(poze_jistic, poze_spotreba)

        # Zjisti, jestli se použila POZE jistič nebo POZE spotřeba
        poze_je_jistic = (poze_jistic > 0 and poze_jistic < poze_spotreba) or (poze_jistic > 0 and poze_spotreba == 0)

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

        # Výpočet jednotkové ceny POZE pro jistič (pokud se použila POZE jistič)
        delka_obdobi = float(vypocet.delka_obdobi_fakturace or 1)
        jednotkova_cena_poze_jistic = poze_jistic / delka_obdobi if delka_obdobi > 0 else 0

        # Výpočet jednotkových cen přepočtených podle poměru období fakturace
        jednotkova_cena_mesicni_plat = float(vypocet.mesicni_plat or 0) / delka_obdobi if delka_obdobi > 0 else 0
        jednotkova_cena_jistic = float(vypocet.platba_za_jistic or 0) / delka_obdobi if delka_obdobi > 0 else 0
        jednotkova_cena_nesitova_infra = float(vypocet.nesitova_infrastruktura or 0) / delka_obdobi if delka_obdobi > 0 else 0

        vypocty_data.append({
            'om': om,
            'vypocet': vypocet,
            'odecet': odecet,
            'poze_minimum': poze_minimum,
            'poze_je_jistic': poze_je_jistic,
            'poze_jistic': poze_jistic,
            'poze_spotreba': poze_spotreba,
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
            'jednotkova_cena_poze_jistic': jednotkova_cena_poze_jistic,
            'jednotkova_cena_dan': jednotkova_cena_dan,
            'jednotkova_cena_mesicni_plat': jednotkova_cena_mesicni_plat,
            'jednotkova_cena_jistic': jednotkova_cena_jistic,
            'jednotkova_cena_nesitova_infra': jednotkova_cena_nesitova_infra
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
            poze_jistic = float(vypocet.poze_dle_jistice or 0)
            poze_spotreba = float(vypocet.poze_dle_spotreby or 0)
            poze_minimum = min(poze_jistic, poze_spotreba)

            # Zjisti, jestli se použila POZE jistič nebo POZE spotřeba
            poze_je_jistic = (poze_jistic > 0 and poze_jistic < poze_spotreba) or (poze_jistic > 0 and poze_spotreba == 0)

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

            # Výpočet jednotkové ceny POZE pro jistič (pokud se použila POZE jistič)
            delka_obdobi = float(vypocet.delka_obdobi_fakturace or 1)
            jednotkova_cena_poze_jistic = poze_jistic / delka_obdobi if delka_obdobi > 0 else 0

            # Výpočet jednotkových cen přepočtených podle poměru období fakturace
            jednotkova_cena_mesicni_plat = float(vypocet.mesicni_plat or 0) / delka_obdobi if delka_obdobi > 0 else 0
            jednotkova_cena_jistic = float(vypocet.platba_za_jistic or 0) / delka_obdobi if delka_obdobi > 0 else 0
            jednotkova_cena_nesitova_infra = float(vypocet.nesitova_infrastruktura or 0) / delka_obdobi if delka_obdobi > 0 else 0

            vypocty_data.append({
                'om': om,
                'vypocet': vypocet,
                'odecet': odecet,
                'poze_minimum': poze_minimum,
                'poze_je_jistic': poze_je_jistic,
                'poze_jistic': poze_jistic,
                'poze_spotreba': poze_spotreba,
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
                'jednotkova_cena_poze_jistic': jednotkova_cena_poze_jistic,
                'jednotkova_cena_dan': jednotkova_cena_dan,
                'jednotkova_cena_mesicni_plat': jednotkova_cena_mesicni_plat,
                'jednotkova_cena_jistic': jednotkova_cena_jistic,
                'jednotkova_cena_nesitova_infra': jednotkova_cena_nesitova_infra
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
            poze_jistic = float(vypocet.poze_dle_jistice or 0)
            poze_spotreba = float(vypocet.poze_dle_spotreby or 0)
            poze_minimum = min(poze_jistic, poze_spotreba)

            # Zjisti, jestli se použila POZE jistič nebo POZE spotřeba
            poze_je_jistic = (poze_jistic > 0 and poze_jistic < poze_spotreba) or (poze_jistic > 0 and poze_spotreba == 0)

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

            # Výpočet jednotkové ceny POZE pro jistič (pokud se použila POZE jistič)
            delka_obdobi = float(vypocet.delka_obdobi_fakturace or 1)
            jednotkova_cena_poze_jistic = poze_jistic / delka_obdobi if delka_obdobi > 0 else 0

            # Výpočet jednotkových cen přepočtených podle poměru období fakturace
            jednotkova_cena_mesicni_plat = float(vypocet.mesicni_plat or 0) / delka_obdobi if delka_obdobi > 0 else 0
            jednotkova_cena_jistic = float(vypocet.platba_za_jistic or 0) / delka_obdobi if delka_obdobi > 0 else 0
            jednotkova_cena_nesitova_infra = float(vypocet.nesitova_infrastruktura or 0) / delka_obdobi if delka_obdobi > 0 else 0

            vypocty_data.append({
                'om': om,
                'vypocet': vypocet,
                'odecet': odecet,
                'poze_minimum': poze_minimum,
                'poze_je_jistic': poze_je_jistic,
                'poze_jistic': poze_jistic,
                'poze_spotreba': poze_spotreba,
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
                'jednotkova_cena_poze_jistic': jednotkova_cena_poze_jistic,
                'jednotkova_cena_dan': jednotkova_cena_dan,
                'jednotkova_cena_mesicni_plat': jednotkova_cena_mesicni_plat,
                'jednotkova_cena_jistic': jednotkova_cena_jistic,
                'jednotkova_cena_nesitova_infra': jednotkova_cena_nesitova_infra
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
