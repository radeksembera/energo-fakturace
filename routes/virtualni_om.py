# -*- coding: utf-8 -*-
"""
Virtuální OM routes - virtuální výpočet pro jedno odběrné místo
"""

from flask import Blueprint, render_template, session, redirect, url_for, flash, request
from models import db, VirtualCenaDistribuce

virtualni_om_bp = Blueprint('virtualni_om', __name__, url_prefix='/virtualni-om')


@virtualni_om_bp.route('/', methods=['GET', 'POST'])
def index():
    """Zobrazí stránku virtuálního výpočtu pro OM"""
    if not session.get("user_id"):
        return redirect("/login")

    user_id = session["user_id"]
    vysledky = None
    formular_data = {}

    if request.method == 'POST':
        # Načti data z formuláře
        formular_data = {
            'rok': request.form.get('rok', type=int),
            'distribuce': request.form.get('distribuce'),
            'distribucni_sazba': request.form.get('distribucni_sazba'),
            'kategorie_jistice': request.form.get('kategorie_jistice'),
            'hodnota_jistice': request.form.get('hodnota_jistice', type=float) or 0,
            'delka_obdobi': request.form.get('delka_obdobi', type=float) or 1,
            'platba_silova_vt': request.form.get('platba_silova_vt', type=float) or 0,
            'platba_silova_nt': request.form.get('platba_silova_nt', type=float) or 0,
            'mesicni_plat': request.form.get('mesicni_plat', type=float) or 0,
            'sazba_dph': request.form.get('sazba_dph', type=float) or 21,
            'spotreba_vt': request.form.get('spotreba_vt', type=float) or 0,
            'spotreba_nt': request.form.get('spotreba_nt', type=float) or 0,
        }

        # Najdi ceny distribuce
        cena_distribuce = VirtualCenaDistribuce.query.filter_by(
            user_id=user_id,
            rok=formular_data['rok'],
            distribuce=formular_data['distribuce'],
            sazba=formular_data['distribucni_sazba'],
            jistic=formular_data['kategorie_jistice']
        ).first()

        if not cena_distribuce:
            flash(f"Ceny distribuce pro zadanou kombinaci nebyly nalezeny.", "warning")
        else:
            # Provádíme výpočty stejně jako v prepocitat_koncove_ceny
            vysledky = vypocitat_koncove_ceny(
                cena_distribuce=cena_distribuce,
                formular_data=formular_data
            )

    return render_template('virtualni_om/index.html',
                         vysledky=vysledky,
                         formular_data=formular_data)


def vypocitat_koncove_ceny(cena_distribuce, formular_data):
    """
    Vypočítá koncové ceny pro virtuální OM.
    Používá stejné výpočty jako prepocitat_koncove_ceny v fakturace.py
    """
    # Vstupní hodnoty
    spotreba_vt = formular_data['spotreba_vt']
    spotreba_nt = formular_data['spotreba_nt']
    celkova_spotreba = spotreba_vt + spotreba_nt
    hodnota_jistice = formular_data['hodnota_jistice']
    delka_obdobi_fakturace = formular_data['delka_obdobi']
    kategorie_jistice = formular_data['kategorie_jistice']
    sazba_dph = formular_data['sazba_dph'] / 100  # Převod z procent

    # Ceny dodavatele z formuláře
    cena_elektriny_vt = formular_data['platba_silova_vt']
    cena_elektriny_nt = formular_data['platba_silova_nt']
    cena_mesicni_plat = formular_data['mesicni_plat']

    # === VÝPOČTY DISTRIBUCE ===

    # 1. platba_za_jistic (vynásobeno poměrem období)
    if kategorie_jistice in ["nad 1x25A za každou 1A", "nad 3x160A za každou 1A", "nad 3x63A za každou 1A"]:
        platba_za_jistic = float(cena_distribuce.platba_za_jistic or 0) * hodnota_jistice * delka_obdobi_fakturace
    else:
        platba_za_jistic = float(cena_distribuce.platba_za_jistic or 0) * delka_obdobi_fakturace

    # 2. platba_za_distribuci_vt = spotreba_vt/1000 * cena_vt
    platba_za_distribuci_vt = (spotreba_vt / 1000) * float(cena_distribuce.platba_za_distribuci_vt or 0)

    # 3. platba_za_distribuci_nt = spotreba_nt/1000 * cena_nt
    platba_za_distribuci_nt = (spotreba_nt / 1000) * float(cena_distribuce.platba_za_distribuci_nt or 0)

    # 4. systemove_sluzby = (spotreba_vt + spotreba_nt)/1000 * cena
    systemove_sluzby = (celkova_spotreba / 1000) * float(cena_distribuce.systemove_sluzby or 0)

    # 5. poze_dle_jistice = cena * hodnota_jistice * poměr období
    # U třífázových jističů (obsahují "3x") násobíme ještě 3 (3 fáze)
    poze_dle_jistice = float(cena_distribuce.poze_dle_jistice or 0) * hodnota_jistice
    if kategorie_jistice and "3x" in kategorie_jistice:
        poze_dle_jistice = poze_dle_jistice * 3
    # Vynásobit poměrem období
    poze_dle_jistice = poze_dle_jistice * delka_obdobi_fakturace

    # 6. poze_dle_spotreby = celkova_spotreba/1000 * cena
    poze_dle_spotreby = (celkova_spotreba / 1000) * float(cena_distribuce.poze_dle_spotreby or 0)

    # 7. nesitova_infrastruktura = cena * poměr období
    nesitova_infrastruktura = float(cena_distribuce.nesitova_infrastruktura or 0) * delka_obdobi_fakturace

    # === VÝPOČTY DODAVATELE ===

    # 8. dan_z_elektriny = cena * celkova_spotreba/1000
    dan_z_elektriny = float(cena_distribuce.dan_z_elektriny or 0) * (celkova_spotreba / 1000)

    # 9. platba_za_elektrinu_vt = spotreba_vt/1000 * cena
    platba_za_elektrinu_vt = (spotreba_vt / 1000) * cena_elektriny_vt

    # 10. platba_za_elektrinu_nt = spotreba_nt/1000 * cena
    platba_za_elektrinu_nt = (spotreba_nt / 1000) * cena_elektriny_nt

    # 11. mesicni_plat = cena * poměr období
    mesicni_plat = cena_mesicni_plat * delka_obdobi_fakturace

    # === CELKOVÉ VÝPOČTY ===

    # 12. zaklad_bez_dph = suma všech složek + MIN(poze_dle_jistice, poze_dle_spotreby)
    poze_minimum = min(poze_dle_jistice, poze_dle_spotreby)
    zaklad_bez_dph = (
        platba_za_jistic +
        platba_za_distribuci_vt +
        platba_za_distribuci_nt +
        systemove_sluzby +
        poze_minimum +
        nesitova_infrastruktura +
        dan_z_elektriny +
        platba_za_elektrinu_vt +
        platba_za_elektrinu_nt +
        mesicni_plat
    )

    # 13. castka_dph = zaklad_bez_dph * sazba_dph
    castka_dph = zaklad_bez_dph * sazba_dph

    # 14. celkem_vc_dph = zaklad_bez_dph + castka_dph
    celkem_vc_dph = zaklad_bez_dph + castka_dph

    return {
        # Distribuce
        'platba_za_jistic': round(platba_za_jistic, 2),
        'platba_za_distribuci_vt': round(platba_za_distribuci_vt, 2),
        'platba_za_distribuci_nt': round(platba_za_distribuci_nt, 2),
        'systemove_sluzby': round(systemove_sluzby, 2),
        'poze_dle_jistice': round(poze_dle_jistice, 2),
        'poze_dle_spotreby': round(poze_dle_spotreby, 2),
        'nesitova_infrastruktura': round(nesitova_infrastruktura, 2),
        # Dodavatel
        'platba_za_elektrinu_vt': round(platba_za_elektrinu_vt, 2),
        'platba_za_elektrinu_nt': round(platba_za_elektrinu_nt, 2),
        'mesicni_plat': round(mesicni_plat, 2),
        'dan_z_elektriny': round(dan_z_elektriny, 2),
        # Celkem
        'poze_minimum': round(poze_minimum, 2),
        'zaklad_bez_dph': round(zaklad_bez_dph, 2),
        'castka_dph': round(castka_dph, 2),
        'celkem_vc_dph': round(celkem_vc_dph, 2),
    }
