# -*- coding: utf-8 -*-
"""
Skript pro vycisteni zkusebnich dat z databaze.
Smaze vsechna data z techto tabulek:
- ceny_distribuce
- ceny_dodavatel
- import_odectu
- vypocty_om
- odecty

Strediska a odberna mista zustanou zachovana.
"""

import sys
import io

# Nastav UTF-8 pro Windows konzoli
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding='utf-8')

from main import app
from models import db, CenaDistribuce, CenaDodavatel, ImportOdečtu, VypocetOM, Odečet

def cleanup_test_data():
    with app.app_context():
        print("=" * 60)
        print("CISTENI ZKUSEBNICH DAT Z DATABAZE")
        print("=" * 60)

        # Zjisti pocty zaznamu pred smazanim
        print("\nPocet zaznamu PRED smazanim:")
        count_ceny_distribuce = CenaDistribuce.query.count()
        count_ceny_dodavatel = CenaDodavatel.query.count()
        count_import_odectu = ImportOdečtu.query.count()
        count_vypocty_om = VypocetOM.query.count()
        count_odecty = Odečet.query.count()

        print(f"  - ceny_distribuce:  {count_ceny_distribuce:>8}")
        print(f"  - ceny_dodavatel:   {count_ceny_dodavatel:>8}")
        print(f"  - import_odectu:    {count_import_odectu:>8}")
        print(f"  - vypocty_om:       {count_vypocty_om:>8}")
        print(f"  - odecty:           {count_odecty:>8}")
        print(f"  {'-' * 40}")
        celkem = count_ceny_distribuce + count_ceny_dodavatel + count_import_odectu + count_vypocty_om + count_odecty
        print(f"  CELKEM:             {celkem:>8}")

        # Potvrzeni
        print(f"\nVAROVANI: Chystate se SMAZAT {celkem} zaznamu!")
        print("\nMazani dat...")

        try:
            # Smaž data z jednotlivých tabulek
            deleted_counts = {}

            # 1. Ceny distribuce
            deleted_counts['ceny_distribuce'] = db.session.query(CenaDistribuce).delete()

            # 2. Ceny dodavatel
            deleted_counts['ceny_dodavatel'] = db.session.query(CenaDodavatel).delete()

            # 3. Import odečtů
            deleted_counts['import_odectu'] = db.session.query(ImportOdečtu).delete()

            # 4. Výpočty OM
            deleted_counts['vypocty_om'] = db.session.query(VypocetOM).delete()

            # 5. Odečty
            deleted_counts['odecty'] = db.session.query(Odečet).delete()

            # Commit vsech zmen
            db.session.commit()

            print("\nData byla uspesne smazana!")
            print("\nPocet smazanych zaznamu:")
            print(f"  - ceny_distribuce:  {deleted_counts['ceny_distribuce']:>8}")
            print(f"  - ceny_dodavatel:   {deleted_counts['ceny_dodavatel']:>8}")
            print(f"  - import_odectu:    {deleted_counts['import_odectu']:>8}")
            print(f"  - vypocty_om:       {deleted_counts['vypocty_om']:>8}")
            print(f"  - odecty:           {deleted_counts['odecty']:>8}")
            print(f"  {'-' * 40}")
            print(f"  CELKEM:             {sum(deleted_counts.values()):>8}")

            # Over, ze tabulky jsou prazdne
            print("\nOvereni:")
            print(f"  - ceny_distribuce:  {CenaDistribuce.query.count():>8} zaznamu")
            print(f"  - ceny_dodavatel:   {CenaDodavatel.query.count():>8} zaznamu")
            print(f"  - import_odectu:    {ImportOdečtu.query.count():>8} zaznamu")
            print(f"  - vypocty_om:       {VypocetOM.query.count():>8} zaznamu")
            print(f"  - odecty:           {Odečet.query.count():>8} zaznamu")

        except Exception as e:
            db.session.rollback()
            print(f"\nChyba pri mazani dat: {str(e)}")
            raise

if __name__ == "__main__":
    cleanup_test_data()
