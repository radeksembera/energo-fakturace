# -*- coding: utf-8 -*-
"""
Migrace: Odstranění sloupce 'jistic' z tabulky 'ceny_dodavatel'

DŮLEŽITÉ:
- Spusťte tento skript pouze jednou!
- Ujistěte se, že máte zálohu databáze před spuštěním
- Jistič zůstává v tabulce ceny_distribuce (to je správně)

Použití:
    python migrate_remove_jistic_from_dodavatel.py
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
    """Spustí migraci - odstraní sloupec jistic z tabulky ceny_dodavatel"""

    with app.app_context():
        try:
            # Zkontroluj zda sloupec existuje
            result = db.session.execute(text("PRAGMA table_info(ceny_dodavatel)"))
            columns = [row[1] for row in result]

            if 'jistic' not in columns:
                print("✅ Sloupec 'jistic' v tabulce 'ceny_dodavatel' již neexistuje.")
                print("   Migrace již byla provedena nebo není potřeba.")
                return

            print("🔄 Zahajuji migraci...")
            print("   Odstraňuji sloupec 'jistic' z tabulky 'ceny_dodavatel'")

            # Pro SQLite musíme vytvořit novou tabulku a zkopírovat data
            if database_url.startswith("sqlite:"):
                print("   Detekována SQLite databáze - použiji metodu rebuild tabulky")

                # 1. Vytvoř novou tabulku bez sloupce jistic
                db.session.execute(text("""
                    CREATE TABLE ceny_dodavatel_new (
                        id INTEGER PRIMARY KEY,
                        stredisko_id INTEGER,
                        obdobi_id INTEGER,
                        distribuce TEXT,
                        sazba TEXT,
                        platba_za_elektrinu_vt NUMERIC,
                        platba_za_elektrinu_nt NUMERIC,
                        mesicni_plat NUMERIC,
                        FOREIGN KEY (stredisko_id) REFERENCES strediska(id),
                        FOREIGN KEY (obdobi_id) REFERENCES obdobi_fakturace(id)
                    )
                """))

                # 2. Zkopíruj data (bez sloupce jistic)
                db.session.execute(text("""
                    INSERT INTO ceny_dodavatel_new
                        (id, stredisko_id, obdobi_id, distribuce, sazba,
                         platba_za_elektrinu_vt, platba_za_elektrinu_nt, mesicni_plat)
                    SELECT
                        id, stredisko_id, obdobi_id, distribuce, sazba,
                        platba_za_elektrinu_vt, platba_za_elektrinu_nt, mesicni_plat
                    FROM ceny_dodavatel
                """))

                # 3. Smaž starou tabulku
                db.session.execute(text("DROP TABLE ceny_dodavatel"))

                # 4. Přejmenuj novou tabulku
                db.session.execute(text("ALTER TABLE ceny_dodavatel_new RENAME TO ceny_dodavatel"))

            else:
                # Pro PostgreSQL můžeme použít přímé DROP COLUMN
                print("   Detekována PostgreSQL databáze - použiji ALTER TABLE DROP COLUMN")
                db.session.execute(text("ALTER TABLE ceny_dodavatel DROP COLUMN jistic"))

            # Commitni změny
            db.session.commit()

            print("✅ Migrace úspěšně dokončena!")
            print("   Sloupec 'jistic' byl odstraněn z tabulky 'ceny_dodavatel'")
            print("   Ceny dodavatele nyní neobsahují informaci o jističi")
            print("")
            print("ℹ️  Poznámka: Jistič zůstává v tabulce 'ceny_distribuce' (to je správně)")

        except Exception as e:
            db.session.rollback()
            print(f"❌ Chyba při migraci: {e}")
            print("")
            print("💡 Tip: Ujistěte se, že máte zálohu databáze před opakováním migrace")
            raise

if __name__ == "__main__":
    print("=" * 70)
    print("MIGRACE: Odstranění sloupce 'jistic' z tabulky 'ceny_dodavatel'")
    print("=" * 70)
    print("")
    print("⚠️  VAROVÁNÍ: Tato operace upraví strukturu databáze!")
    print("   Ujistěte se, že máte zálohu databáze před pokračováním.")
    print("")

    odpoved = input("Chcete pokračovat? (ano/ne): ").strip().lower()

    if odpoved in ['ano', 'a', 'yes', 'y']:
        run_migration()
    else:
        print("❌ Migrace zrušena uživatelem.")
