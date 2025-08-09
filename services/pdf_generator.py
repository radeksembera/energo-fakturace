from flask import session, redirect
from models import (Stredisko, Faktura, ZalohovaFaktura, 
                   InfoDodavatele, InfoOdberatele, VypocetOM, OdberneMisto, Odečet)
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
import io

def get_faktura_data(stredisko_id, rok, mesic):
    """Sdílená funkce pro získání dat faktury (pro HTML i PDF)"""
    if not session.get("user_id"):
        return None, redirect("/login")

    stredisko = Stredisko.query.get_or_404(stredisko_id)
    if stredisko.user_id != session["user_id"]:
        return None, ("Nepovolený přístup", 403)

    # Zatím není implementováno ObdobiFakturace
    # Placeholder implementation
    faktura = Faktura.query.filter_by(stredisko_id=stredisko_id).first()
    zaloha = ZalohovaFaktura.query.filter_by(stredisko_id=stredisko_id).first()
    dodavatel = InfoDodavatele.query.filter_by(stredisko_id=stredisko_id).first()
    odberatel = InfoOdberatele.query.filter_by(stredisko_id=stredisko_id).first()
    
    # Načti výpočty
    vypocty = VypocetOM.query.join(OdberneMisto).filter(OdberneMisto.stredisko_id == stredisko_id).all()

    if not vypocty:
        return None, ("Nejsou k dispozici výpočty pro vybrané období.", 400)

    # Načti odečty
    odecty = Odečet.query.filter_by(stredisko_id=stredisko_id).all()

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
        'dofakturace_bonus': dofakturace_bonus,
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
        'obdobi': None,  # zatím neimplementováno
        'faktura': faktura,
        'zaloha': zaloha,
        'dodavatel': dodavatel,
        'odberatel': odberatel,
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
    """Registrace českých fontů pro PDF"""
    # Můžete přidat registraci vlastních fontů zde
    pass