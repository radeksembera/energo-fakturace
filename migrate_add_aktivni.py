#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Migrační script pro přidání sloupce 'aktivni' do tabulky 'strediska'
Datum: 2025-12-20
"""

import os
import sys

# Nastav UTF-8 kódování pro stdout
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from dotenv import load_dotenv
from main import app
from models import db

def migrate_add_aktivni():
    """Přidá sloupec aktivni do tabulky strediska"""
    print("Spouštím migraci: Přidání sloupce 'aktivni' do tabulky 'strediska'...")

    # Načti environment proměnné
    load_dotenv()

    with app.app_context():
        try:
            # SQL příkaz pro přidání sloupce
            # Podporuje PostgreSQL i SQLite
            sql = """
            ALTER TABLE strediska
            ADD COLUMN IF NOT EXISTS aktivni BOOLEAN DEFAULT TRUE NOT NULL;
            """

            # Pro SQLite použij jiný příkaz (SQLite nepodporuje IF NOT EXISTS na ALTER TABLE)
            database_url = app.config['SQLALCHEMY_DATABASE_URI']

            if 'sqlite' in database_url:
                # Pro SQLite - kontrola existence sloupce
                result = db.session.execute(db.text("PRAGMA table_info(strediska)"))
                columns = [row[1] for row in result]

                if 'aktivni' not in columns:
                    print("SQLite detekováno - přidávám sloupec 'aktivni'...")
                    db.session.execute(db.text("""
                        ALTER TABLE strediska
                        ADD COLUMN aktivni BOOLEAN DEFAULT TRUE NOT NULL
                    """))
                else:
                    print("Sloupec 'aktivni' již existuje v tabulce (SQLite)")
                    return True
            else:
                # PostgreSQL
                print("PostgreSQL detekováno - přidávám sloupec 'aktivni'...")
                db.session.execute(db.text(sql))

            # Ujisti se, že všechna existující střediska jsou aktivní
            db.session.execute(db.text("""
                UPDATE strediska
                SET aktivni = TRUE
                WHERE aktivni IS NULL
            """))

            db.session.commit()

            # Ověř migraci
            result = db.session.execute(db.text("""
                SELECT COUNT(*) as total,
                       SUM(CASE WHEN aktivni = TRUE THEN 1 ELSE 0 END) as aktivni_count
                FROM strediska
            """))
            row = result.fetchone()

            print(f"✅ Migrace úspěšně dokončena!")
            print(f"   Celkem středisek: {row[0]}")
            print(f"   Aktivních středisek: {row[1]}")

            return True

        except Exception as e:
            db.session.rollback()
            print(f"❌ CHYBA při migraci: {e}")
            print("\nPokud sloupec 'aktivni' již existuje, migrace není nutná.")
            return False

    return True

if __name__ == "__main__":
    success = migrate_add_aktivni()
    if success:
        print("\n✅ Migrace proběhla úspěšně!")
        print("Můžete nyní restartovat aplikaci.")
    else:
        print("\n❌ Migrace selhala!")
        exit(1)
