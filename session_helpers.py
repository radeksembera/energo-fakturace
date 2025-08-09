"""
session_helpers.py
Pomocné funkce pro správu vybraného období v uživatelské session
"""

from datetime import datetime
from flask import session
from models import ObdobiFakturace

def get_default_obdobi_for_stredisko(stredisko_id):
    """
    Získá výchozí období pro středisko (aktuální měsíc/rok)
    Pokud aktuální měsíc neexistuje, vrátí nejnovější dostupné období
    """
    current_date = datetime.now()
    current_year = current_date.year
    current_month = current_date.month
    
    print(f"🔍 DEBUG: Hledám výchozí období pro středisko {stredisko_id}")
    print(f"🔍 DEBUG: Aktuální datum: {current_year}/{current_month:02d}")
    
    # Najdi aktuální období
    obdobi = ObdobiFakturace.query.filter_by(
        stredisko_id=stredisko_id,
        rok=current_year,
        mesic=current_month
    ).first()
    
    if obdobi:
        print(f"✅ DEBUG: Nalezeno aktuální období {obdobi.rok}/{obdobi.mesic:02d} (ID: {obdobi.id})")
        return obdobi
    
    print(f"⚠️ DEBUG: Aktuální období {current_year}/{current_month:02d} neexistuje, hledám nejnovější")
    
    # Pokud aktuální měsíc neexistuje, vezmi nejnovější dostupné
    obdobi = ObdobiFakturace.query.filter_by(
        stredisko_id=stredisko_id
    ).order_by(ObdobiFakturace.rok.desc(), ObdobiFakturace.mesic.desc()).first()
    
    if obdobi:
        print(f"✅ DEBUG: Nalezeno nejnovější období {obdobi.rok}/{obdobi.mesic:02d} (ID: {obdobi.id})")
    else:
        print(f"❌ DEBUG: Žádné období pro středisko {stredisko_id} neexistuje")
    
    return obdobi

def get_session_obdobi(stredisko_id):
    """
    Získá období pro středisko ze session nebo nastaví výchozí
    """
    session_key = f"vybrane_obdobi_{stredisko_id}"
    
    print(f"🔍 DEBUG: Hledám období pro středisko {stredisko_id}")
    print(f"🔍 DEBUG: Session key: {session_key}")
    print(f"🔍 DEBUG: Session obsahuje: {list(session.keys())}")
    
    # Pokud není v session, nastav výchozí
    if session_key not in session:
        print(f"🔍 DEBUG: Klíč {session_key} NENÍ v session, nastavuji výchozí")
        default_obdobi = get_default_obdobi_for_stredisko(stredisko_id)
        if default_obdobi:
            session[session_key] = default_obdobi.id
            print(f"✅ DEBUG: Nastaveno výchozí období {default_obdobi.rok}/{default_obdobi.mesic:02d} (ID: {default_obdobi.id})")
            return default_obdobi
        print(f"❌ DEBUG: Žádné výchozí období nenalezeno")
        return None
    
    # Načti z session
    obdobi_id = session[session_key]
    print(f"🔍 DEBUG: Načítám obdobi_id {obdobi_id} ze session")
    
    obdobi = ObdobiFakturace.query.filter_by(
        id=obdobi_id,
        stredisko_id=stredisko_id
    ).first()
    
    if obdobi:
        print(f"✅ DEBUG: Nalezeno období {obdobi.rok}/{obdobi.mesic:02d} ze session")
    else:
        print(f"❌ DEBUG: Období ID {obdobi_id} neexistuje, nastavuji nové výchozí")
        # Pokud období už neexistuje, nastav nové výchozí
        default_obdobi = get_default_obdobi_for_stredisko(stredisko_id)
        if default_obdobi:
            session[session_key] = default_obdobi.id
        return default_obdobi
    
    return obdobi

def set_session_obdobi(stredisko_id, obdobi_id):
    """
    Nastaví období pro středisko do session
    """
    session_key = f"vybrane_obdobi_{stredisko_id}"
    session[session_key] = obdobi_id
    print(f"🔄 Session: Nastaveno období {obdobi_id} pro středisko {stredisko_id}")

def handle_obdobi_selection(stredisko_id, request_args):
    """
    Zpracuje výběr období z GET parametrů a aktualizuje session
    Použije se v každé route, která má výběr období
    
    Args:
        stredisko_id: ID střediska
        request_args: request.args z Flask
    
    Returns:
        ObdobiFakturace objekt nebo None
    """
    # Pokud je v URL parametru nové období, ulož do session
    new_obdobi_id = request_args.get("obdobi_id", type=int)
    if new_obdobi_id:
        # Ověř, že období patří střediska
        obdobi = ObdobiFakturace.query.filter_by(
            id=new_obdobi_id,
            stredisko_id=stredisko_id
        ).first()
        if obdobi:
            set_session_obdobi(stredisko_id, new_obdobi_id)
            print(f"✅ Session: Uživatel vybral období {obdobi.rok}/{obdobi.mesic:02d}")
    
    # Vrať aktuální období ze session
    return get_session_obdobi(stredisko_id)

# V session_helpers.py - oprava funkce handle_obdobi_from_rok_mesic

def handle_obdobi_from_rok_mesic(stredisko_id, request_args):
    """
    Speciální funkce pro ceny dodavatele - převede rok/měsíc na obdobi_id
    a uloží do session. Pokud období neexistuje, vytvoří ho.
    
    Args:
        stredisko_id: ID střediska
        request_args: request.args z Flask (očekává 'rok' a 'mesic')
    
    Returns:
        ObdobiFakturace objekt nebo None
    """
    url_rok = request_args.get("rok", type=int)
    url_mesic = request_args.get("mesic", type=int)
    
    if url_rok and url_mesic:
        # Najdi období podle roku/měsíce
        obdobi = ObdobiFakturace.query.filter_by(
            stredisko_id=stredisko_id,
            rok=url_rok,
            mesic=url_mesic
        ).first()
        
        if not obdobi:
            # ✅ OPRAVA: Pokud období neexistuje, vytvoř ho
            from models import db  # Import zde aby se předešlo circular import
            obdobi = ObdobiFakturace(
                stredisko_id=stredisko_id,
                rok=url_rok,
                mesic=url_mesic
            )
            db.session.add(obdobi)
            db.session.commit()
            print(f"✅ Session: Vytvořeno nové období {url_rok}/{url_mesic:02d} (ID: {obdobi.id})")
        
        # Ulož do session
        set_session_obdobi(stredisko_id, obdobi.id)
        print(f"✅ Session: Uživatel vybral období {url_rok}/{url_mesic:02d} (ID: {obdobi.id})")
        return obdobi
    
    # Pokud nejsou URL parametry, vrať aktuální období ze session
    return get_session_obdobi(stredisko_id)

def clear_session_obdobi(stredisko_id):
    """
    Vymaže uložené období pro středisko ze session
    Užitečné při přepínání mezi středisky
    """
    session_key = f"vybrane_obdobi_{stredisko_id}"
    if session_key in session:
        del session[session_key]
        print(f"🗑️ Session: Vymazáno období pro středisko {stredisko_id}")

def get_session_debug_info():
    """
    Debug funkce - vrátí informace o uložených obdobích v session
    """
    obdobi_keys = [key for key in session.keys() if key.startswith("vybrane_obdobi_")]
    debug_info = {}
    
    for key in obdobi_keys:
        stredisko_id = key.replace("vybrane_obdobi_", "")
        obdobi_id = session[key]
        
        # Načti období pro debug info
        obdobi = ObdobiFakturace.query.get(obdobi_id)
        if obdobi:
            debug_info[stredisko_id] = f"{obdobi.rok}/{obdobi.mesic:02d} (ID: {obdobi_id})"
        else:
            debug_info[stredisko_id] = f"ID: {obdobi_id} (neexistuje)"
    
    return debug_info