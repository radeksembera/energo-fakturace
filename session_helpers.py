"""
session_helpers.py
Pomocné funkce pro správu vybraného období v uživatelské session
Zjednodušená verzia bez ObdobiFakturace modelu
"""

from datetime import datetime
from flask import session

def get_default_obdobi_for_stredisko(stredisko_id):
    """
    Zatím neimplementováno - ObdobiFakturace model neexistuje
    """
    return None

def get_session_obdobi(stredisko_id):
    """
    Zatím neimplementováno - ObdobiFakturace model neexistuje
    """
    return None

def set_session_obdobi(stredisko_id, obdobi_id):
    """
    Nastav vybrané období do session
    """
    session_key = f"vybrane_obdobi_{stredisko_id}"
    session[session_key] = obdobi_id
    print(f"✅ DEBUG: Období {obdobi_id} nastaveno pro středisko {stredisko_id}")

def handle_obdobi_selection(stredisko_id, request_form):
    """
    Zatím neimplementováno
    """
    return None

def handle_obdobi_from_rok_mesic(stredisko_id, rok, mesic):
    """
    Zatím neimplementováno
    """
    return None