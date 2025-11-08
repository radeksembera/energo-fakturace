# -*- coding: utf-8 -*-
"""
Migrace: Přidání sloupce 'spotreba_om' do tabulky 'vypocty_om'

DŮLEŽITÉ:
- Spusťte tento skript pouze jednou!
- Ujistěte se, že máte zálohu databáze před spuštěním
- Sloupec bude obsahovat celkovou spotřebu OM (VT + NT) v kWh

Použití:
    python migrate_add_spotreba_om.py
"""

from flask import Flask
from models import db
import os
from sqlalchemy import text

# Load environment variables
from dotenv import load_dotenv
if os.path.exists('.env'):
    load_dotenv()

# Flask app configuration
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "tajny_klic")

# Database configuration
database_url = os.environ.get("DATABASE_URL") or os.environ.get("SQLALCHEMY_DATABASE_URI")
if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

if not database_url:
    database_url = "sqlite:///instance/energo_fakturace.db"

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize database
db.init_app(app)

def run_migration():
    """Spustí migraci - přidá sloupec spotreba_om do tabulky vypocty_om"""

    with app.app_context():
        try:
            # Zkontroluj zda sloupec již existuje
            if database_url.startswith("sqlite:"):
                result = db.session.execute(text("PRAGMA table_info(vypocty_om)"))
                columns = [row[1] for row in result]
            else:
                # PostgreSQL
                result = db.session.execute(text("""
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name='vypocty_om'
                """))
                columns = [row[0] for row in result]

            if 'spotreba_om' in columns:
                print("OK: Sloupec 'spotreba_om' v tabulce 'vypocty_om' jiz existuje.")
                print("    Migrace jiz byla provedena nebo neni potreba.")
                return

            print("Zahajuji migraci...")
            print("    Pridavam sloupec 'spotreba_om' do tabulky 'vypocty_om'")

            # Přidej sloupec spotreba_om
            db.session.execute(text("""
                ALTER TABLE vypocty_om
                ADD COLUMN spotreba_om NUMERIC
            """))

            # Commitni změny
            db.session.commit()

            print("OK: Migrace uspesne dokoncena!")
            print("    Sloupec 'spotreba_om' byl pridan do tabulky 'vypocty_om'")
            print("    Tento sloupec bude obsahovat celkovou spotrebu OM (VT + NT) v kWh")
            print("")
            print("Poznamka: Hodnoty se naplni pri pristim prepoctu koncovych cen")

        except Exception as e:
            db.session.rollback()
            print(f"CHYBA pri migraci: {e}")
            print("")
            print("Tip: Ujistete se, ze mate zalohu databaze pred opakovanim migrace")
            raise

if __name__ == "__main__":
    print("=" * 70)
    print("MIGRACE: Pridani sloupce 'spotreba_om' do tabulky 'vypocty_om'")
    print("=" * 70)
    print("")
    print("VAROVANI: Tato operace upravi strukturu databaze!")
    print("   Ujistete se, ze mate zalohu databaze pred pokracovanim.")
    print("")

    odpoved = input("Chcete pokracovat? (ano/ne): ").strip().lower()

    if odpoved in ['ano', 'a', 'yes', 'y']:
        run_migration()
    else:
        print("Migrace zrusena uzivatelem.")
