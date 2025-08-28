"""
session_helpers.py
Pomocné funkce pro správu vybraného období v uživatelské session
"""

from datetime import datetime
from flask import session, request
from models import ObdobiFakturace

def get_current_obdobi():
    """
    Vrátí aktuální období (aktuální měsíc - 1)
    """
    now = datetime.now()
    if now.month == 1:
        return 2025, 12  # Prosinec předchozího roku
    else:
        return now.year, now.month - 1

def get_dostupna_obdobi_pro_stredisko(stredisko_id):
    """
    Vrátí všechna dostupná období pro dané středisko
    """
    obdobi = ObdobiFakturace.query.filter_by(stredisko_id=stredisko_id)\
        .order_by(ObdobiFakturace.rok, ObdobiFakturace.mesic).all()
    return obdobi

def get_session_obdobi(stredisko_id):
    """
    Získá vybrané období ze session nebo vrátí default (aktuální měsíc - 1)
    """
    session_key = f"vybrane_obdobi_{stredisko_id}"
    
    # Pokud je v session uloženo období, použij ho
    if session_key in session:
        rok, mesic = session[session_key]
        # Ověř že období stále existuje v databázi
        obdobi = ObdobiFakturace.query.filter_by(
            stredisko_id=stredisko_id, 
            rok=rok, 
            mesic=mesic
        ).first()
        if obdobi:
            return obdobi
    
    # Jinak nastav default (aktuální měsíc - 1)
    default_rok, default_mesic = get_current_obdobi()
    obdobi = ObdobiFakturace.query.filter_by(
        stredisko_id=stredisko_id,
        rok=default_rok,
        mesic=default_mesic
    ).first()
    
    if obdobi:
        set_session_obdobi(stredisko_id, obdobi.rok, obdobi.mesic)
        return obdobi
    
    # Pokud default neexistuje, vezmi první dostupné období
    prvni_obdobi = ObdobiFakturace.query.filter_by(stredisko_id=stredisko_id)\
        .order_by(ObdobiFakturace.rok, ObdobiFakturace.mesic).first()
    
    if prvni_obdobi:
        set_session_obdobi(stredisko_id, prvni_obdobi.rok, prvni_obdobi.mesic)
        return prvni_obdobi
    
    return None

def set_session_obdobi(stredisko_id, rok, mesic):
    """
    Nastav vybrané období do session
    """
    session_key = f"vybrane_obdobi_{stredisko_id}"
    session[session_key] = (rok, mesic)
    print(f"✅ Session: Období {rok}/{mesic:02d} nastaveno pro středisko {stredisko_id}")

def handle_obdobi_selection(stredisko_id, request_args):
    """
    Zpracuje výběr období z URL parametrů nebo formuláře
    """
    # Kontrola URL parametru ?obdobi_id=123
    obdobi_id = request_args.get('obdobi_id', type=int)
    
    if obdobi_id:
        # Najdi období podle ID v databázi
        obdobi = ObdobiFakturace.query.filter_by(
            id=obdobi_id,
            stredisko_id=stredisko_id
        ).first()
        
        if obdobi:
            set_session_obdobi(stredisko_id, obdobi.rok, obdobi.mesic)
            return obdobi
    
    # Kontrola URL parametrů ?rok=2025&mesic=7 (zpětná kompatibilita)
    rok = request_args.get('rok', type=int)
    mesic = request_args.get('mesic', type=int)
    
    if rok and mesic:
        # Najdi období v databázi
        obdobi = ObdobiFakturace.query.filter_by(
            stredisko_id=stredisko_id,
            rok=rok,
            mesic=mesic
        ).first()
        
        if obdobi:
            set_session_obdobi(stredisko_id, rok, mesic)
            return obdobi
    
    # Pokud není v URL, vrať aktuálně vybrané období
    return get_session_obdobi(stredisko_id)

def get_obdobi_display_name(rok, mesic):
    """
    Vrátí formátovaný název období (např. "Červenec 2025")
    """
    mesice = {
        1: "Leden", 2: "Únor", 3: "Březen", 4: "Duben", 
        5: "Květen", 6: "Červen", 7: "Červenec", 8: "Srpen",
        9: "Září", 10: "Říjen", 11: "Listopad", 12: "Prosinec"
    }
    return f"{mesice.get(mesic, mesic)} {rok}"

def handle_obdobi_from_rok_mesic(stredisko_id, rok, mesic):
    """
    Najde období podle roku a měsíce a nastaví ho do session
    """
    if rok and mesic:
        obdobi = ObdobiFakturace.query.filter_by(
            stredisko_id=stredisko_id,
            rok=rok,
            mesic=mesic
        ).first()
        
        if obdobi:
            set_session_obdobi(stredisko_id, rok, mesic)
            return obdobi
    
    # Pokud období neexistuje, vrať aktuálně vybrané
    return get_session_obdobi(stredisko_id)