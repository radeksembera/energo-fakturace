# -*- coding: utf-8 -*-
"""
Generátor vzorového Excel souboru pro import cen dodavatele (BEZ sloupce jistič)

Tento skript vytvoří vzorový Excel soubor s následujícími sloupci:
- distribuce (např. ČEZ, EGD, PRE)
- sazba (např. C01d, C02d)
- platba_za_elektrinu_vt (Kč/MWh)
- platba_za_elektrinu_nt (Kč/MWh)
- mesicni_plat (Kč/měsíc)

DŮLEŽITÉ:
- Sloupec 'jistic' byl ODSTRANĚN z cen dodavatele
- Cena dodavatele platí pro všechny jističe v rámci dané distribuce a sazby
- Pro ceny DISTRIBUCE se jistič stále používá (to zůstává beze změny)

Použití:
    python generate_ceny_dodavatele_template.py
"""

import pandas as pd
import os

def generate_template():
    """Vytvoří vzorový Excel soubor pro import cen dodavatele"""

    # Vzorová data - ceny dodavatele BEZ sloupce jistic
    data = {
        'distribuce': ['ČEZ', 'ČEZ', 'EGD', 'EGD', 'PRE', 'PRE'],
        'sazba': ['C01d', 'C02d', 'C01d', 'C02d', 'C01d', 'C02d'],
        'platba_za_elektrinu_vt': [3009.00, 2950.00, 3100.00, 3050.00, 3000.00, 2940.00],
        'platba_za_elektrinu_nt': [2850.00, 2800.00, 2920.00, 2870.00, 2840.00, 2790.00],
        'mesicni_plat': [190.00, 220.00, 195.00, 225.00, 188.00, 218.00]
    }

    # Vytvoř DataFrame
    df = pd.DataFrame(data)

    # Vytvoř složku static/templates pokud neexistuje
    output_dir = 'static/templates'
    os.makedirs(output_dir, exist_ok=True)

    # Název výstupního souboru
    output_file = os.path.join(output_dir, 'ceny_dodavatele_import.xlsx')

    # Ulož do Excel souboru
    df.to_excel(output_file, index=False, sheet_name='Ceny')

    print("Vzorovy soubor byl vytvoren!")
    print(f"   Umisteni: {output_file}")
    print("")
    print("Sloupce v souboru:")
    print("   - distribuce: Nazev distribuce (CEZ, EGD, PRE)")
    print("   - sazba: Distribucni sazba (C01d, C02d, atd.)")
    print("   - platba_za_elektrinu_vt: Cena za silovou elektrinu VT (Kc/MWh)")
    print("   - platba_za_elektrinu_nt: Cena za silovou elektrinu NT (Kc/MWh)")
    print("   - mesicni_plat: Mesicni staly plat (Kc/mesic)")
    print("")
    print("Poznamka:")
    print("   - Sloupec 'jistic' byl ODSTRANEN - cena dodavatele plati")
    print("     pro vsechny jistice v ramci dane distribuce a sazby")
    print("   - Pro ceny DISTRIBUCE se jistic stale pouziva")

    return output_file

if __name__ == "__main__":
    print("=" * 70)
    print("Generator vzoroveho Excel souboru pro ceny dodavatele")
    print("=" * 70)
    print("")

    try:
        output_file = generate_template()
        print("")
        print("Hotovo! Soubor muzete pouzit jako vzor pro import cen dodavatele.")

    except Exception as e:
        print(f"Chyba pri generovani souboru: {e}")
        raise
