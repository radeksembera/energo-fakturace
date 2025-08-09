import pandas as pd
# ObdobiFakturace model currently not available

def safe_excel_string(value, zfill_length=None):
    """Bezpečně převede Excel hodnotu na string s ošetřením vedoucích nul"""
    if pd.isna(value) or value == "":
        return ""
    if isinstance(value, (int, float)) and zfill_length:
        return f"{int(value):0{zfill_length}d}"
    return str(value).strip()

def safe_sum_filter(values, attribute=None):
    """Bezpečně sečte hodnoty s filtrováním None/NaN hodnot"""
    if not values:
        return 0.0
    
    if attribute:
        # Pokud je zadán atribut, extrahuj hodnoty z objektů
        numeric_values = []
        for item in values:
            val = getattr(item, attribute, None)
            if val is not None and not pd.isna(val):
                try:
                    numeric_values.append(float(val))
                except (ValueError, TypeError):
                    pass
    else:
        # Přímo sečti hodnoty
        numeric_values = []
        for val in values:
            if val is not None and not pd.isna(val):
                try:
                    numeric_values.append(float(val))
                except (ValueError, TypeError):
                    pass
    
    return sum(numeric_values)

def get_unified_obdobi_list(stredisko_id=None):
    """
    Vrátí jednotný seznam období pro všechny selectboxy v aplikaci
    Zatím není implementováno - ObdobiFakturace model neexistuje
    """
    return []

def get_obdobi_filter(stredisko_id):
    """Vrati filter pro období konkrétního střediska"""
    return []

def get_unified_obdobi_template(stredisko_id):
    """Vrátí data pro template - obdobi pro konkrétní středisko"""
    return []