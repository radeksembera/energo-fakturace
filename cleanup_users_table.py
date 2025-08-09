"""
cleanup_users_table.py
Zjednodušení users tabulky - odstranění zbytečných sloupců
"""

from main import app
from models import db
from sqlalchemy import text

def check_current_state():
    """Zkontroluje současný stav před cleanup"""
    
    print("🔍 Kontrola současného stavu před cleanup...")
    
    with app.app_context():
        try:
            # Zkontroluj aktuální sloupce v users tabulce
            columns_query = text("""
                SELECT column_name, data_type, is_nullable 
                FROM information_schema.columns 
                WHERE table_name = 'users' 
                ORDER BY ordinal_position;
            """)
            
            columns = db.session.execute(columns_query).fetchall()
            
            print(f"📋 Aktuální sloupce v users tabulce:")
            has_username = False
            has_jmeno = False
            has_email = False
            
            for col in columns:
                column_name, data_type, nullable = col
                print(f"   - {column_name} ({data_type}) {'NULL' if nullable == 'YES' else 'NOT NULL'}")
                
                if column_name == 'username':
                    has_username = True
                elif column_name == 'jmeno':
                    has_jmeno = True
                elif column_name == 'email':
                    has_email = True
            
            print(f"\n🔍 Analýza sloupců:")
            print(f"   username: {'✅ existuje' if has_username else '❌ neexistuje'}")
            print(f"   jmeno: {'✅ existuje' if has_jmeno else '❌ neexistuje'}")
            print(f"   email: {'✅ existuje' if has_email else '❌ neexistuje'}")
            
            if not has_email:
                print(f"❌ CHYBA: Email sloupec neexistuje! Nelze pokračovat.")
                return False
            
            # Zobraz data uživatelů
            users_query = text("SELECT id, username, email, is_admin FROM users ORDER BY id;")
            users = db.session.execute(users_query).fetchall()
            
            print(f"\n👥 Aktuální uživatelé ({len(users)}):")
            for user in users:
                user_id, username, email, is_admin = user
                admin_badge = "👑" if is_admin else "👤"
                print(f"   {admin_badge} ID:{user_id} | username:'{username}' | email:'{email}'")
            
            return True, has_username, has_jmeno
            
        except Exception as e:
            print(f"❌ Chyba při kontrole stavu: {e}")
            return False, False, False

def step1_drop_username_column(has_username):
    """Krok 1: Odstranění username sloupce"""
    
    if not has_username:
        print("\n📋 KROK 1: Odstranění username sloupce")
        print("-" * 50)
        print("   ℹ️  Username sloupec už neexistuje - přeskakuji")
        return True
    
    print("\n📋 KROK 1: Odstranění username sloupce")
    print("-" * 50)
    
    try:
        print("   ⚠️  Odstraňujem sloupec 'username'...")
        
        # PostgreSQL syntax pro odstranění sloupce
        db.session.execute(text("ALTER TABLE users DROP COLUMN IF EXISTS username;"))
        
        db.session.commit()
        print("   ✅ Sloupec 'username' úspěšně odstraněn")
        return True
        
    except Exception as e:
        print(f"   ❌ Chyba při odstraňování username: {e}")
        db.session.rollback()
        return False

def step2_drop_jmeno_column(has_jmeno):
    """Krok 2: Odstranění jmeno sloupce"""
    
    if not has_jmeno:
        print("\n📋 KROK 2: Odstranění jmeno sloupce")
        print("-" * 50)
        print("   ℹ️  Jmeno sloupec už neexistuje - přeskakuji")
        return True
    
    print("\n📋 KROK 2: Odstranění jmeno sloupce")
    print("-" * 50)
    
    try:
        print("   ⚠️  Odstraňujem sloupec 'jmeno'...")
        
        # PostgreSQL syntax pro odstranění sloupce
        db.session.execute(text("ALTER TABLE users DROP COLUMN IF EXISTS jmeno;"))
        
        db.session.commit()
        print("   ✅ Sloupec 'jmeno' úspěšně odstraněn")
        return True
        
    except Exception as e:
        print(f"   ❌ Chyba při odstraňování jmeno: {e}")
        db.session.rollback()
        return False

def step3_add_email_unique_constraint():
    """Krok 3: Přidání UNIQUE constraint na email (pokud neexistuje)"""
    
    print("\n📋 KROK 3: Nastavení email jako UNIQUE")
    print("-" * 50)
    
    try:
        # Zkontroluj, jestli už email má UNIQUE constraint
        constraint_query = text("""
            SELECT constraint_name 
            FROM information_schema.table_constraints 
            WHERE table_name = 'users' 
            AND constraint_type = 'UNIQUE' 
            AND constraint_name LIKE '%email%';
        """)
        
        existing_constraints = db.session.execute(constraint_query).fetchall()
        
        if existing_constraints:
            print(f"   ℹ️  Email už má UNIQUE constraint: {existing_constraints[0][0]}")
            return True
        
        print("   ➕ Přidávám UNIQUE constraint na email...")
        
        # Nejdřív zkontroluj, jestli nejsou duplicitní emaily
        duplicates_query = text("""
            SELECT email, COUNT(*) as count 
            FROM users 
            GROUP BY email 
            HAVING COUNT(*) > 1;
        """)
        
        duplicates = db.session.execute(duplicates_query).fetchall()
        
        if duplicates:
            print(f"   ⚠️  Nalezeny duplicitní emaily:")
            for dup in duplicates:
                print(f"      - '{dup[0]}' ({dup[1]}x)")
            print(f"   ❌ Nelze přidat UNIQUE constraint s duplicitními hodnotami!")
            return False
        
        # Přidej UNIQUE constraint
        db.session.execute(text("ALTER TABLE users ADD CONSTRAINT users_email_unique UNIQUE (email);"))
        
        db.session.commit()
        print("   ✅ UNIQUE constraint na email přidán")
        return True
        
    except Exception as e:
        print(f"   ❌ Chyba při přidávání UNIQUE constraint: {e}")
        db.session.rollback()
        return False

def step4_cleanup_poznamka_column():
    """Krok 4: Volitelně odstranit i poznamka sloupec (pokud není potřeba)"""
    
    print("\n📋 KROK 4: Cleanup poznamka sloupce")
    print("-" * 50)
    
    try:
        # Zkontroluj, jestli poznamka obsahuje nějaká data
        poznamka_data_query = text("SELECT COUNT(*) FROM users WHERE poznamka IS NOT NULL AND poznamka != '';")
        count_with_poznamka = db.session.execute(poznamka_data_query).fetchone()[0]
        
        print(f"   📊 Uživatelů s poznámkou: {count_with_poznamka}")
        
        if count_with_poznamka > 0:
            print("   ℹ️  Poznamka sloupec obsahuje data - ponechávám")
            return True
        
        response = input("   ❓ Odstranit i poznamka sloupec (je prázdný)? (y/N): ")
        if response.lower() == 'y':
            print("   ⚠️  Odstraňujem sloupec 'poznamka'...")
            db.session.execute(text("ALTER TABLE users DROP COLUMN IF EXISTS poznamka;"))
            db.session.commit()
            print("   ✅ Sloupec 'poznamka' odstraněn")
        else:
            print("   ℹ️  Poznamka sloupec ponechán")
        
        return True
        
    except Exception as e:
        print(f"   ❌ Chyba při cleanup poznamka: {e}")
        db.session.rollback()
        return False

def final_verification():
    """Finální ověření cleanup"""
    
    print("\n🔍 FINÁLNÍ OVĚŘENÍ CLEANUP")
    print("=" * 50)
    
    try:
        # Zkontroluj novou strukturu tabulky
        columns_query = text("""
            SELECT column_name, data_type, is_nullable 
            FROM information_schema.columns 
            WHERE table_name = 'users' 
            ORDER BY ordinal_position;
        """)
        
        columns = db.session.execute(columns_query).fetchall()
        
        print(f"📋 Finální struktura users tabulky:")
        essential_columns = ['id', 'email', 'password_hash', 'is_admin', 'is_active']
        found_essential = []
        
        for col in columns:
            column_name, data_type, nullable = col
            is_essential = "🔹" if column_name in essential_columns else "  "
            print(f"   {is_essential} {column_name} ({data_type}) {'NULL' if nullable == 'YES' else 'NOT NULL'}")
            
            if column_name in essential_columns:
                found_essential.append(column_name)
        
        # Zkontroluj, že máme všechny důležité sloupce
        missing_essential = set(essential_columns) - set(found_essential)
        if missing_essential:
            print(f"❌ Chybí důležité sloupce: {missing_essential}")
            return False
        
        # Zkontroluj UNIQUE constraint na email
        constraint_query = text("""
            SELECT constraint_name 
            FROM information_schema.table_constraints 
            WHERE table_name = 'users' 
            AND constraint_type = 'UNIQUE' 
            AND constraint_name LIKE '%email%';
        """)
        
        email_constraints = db.session.execute(constraint_query).fetchall()
        email_unique = len(email_constraints) > 0
        
        print(f"\n🔍 Kontrola constraints:")
        print(f"   Email UNIQUE: {'✅' if email_unique else '❌'}")
        
        # Zobraz finální data
        users_query = text("SELECT id, email, is_admin, is_active FROM users ORDER BY id;")
        users = db.session.execute(users_query).fetchall()
        
        print(f"\n👥 Finální seznam uživatelů ({len(users)}):")
        for user in users:
            user_id, email, is_admin, is_active = user
            admin_badge = "👑" if is_admin else "👤"
            status_badge = "✅" if is_active else "❌"
            print(f"   {admin_badge} ID:{user_id} | {email} {status_badge}")
        
        print(f"\n🎉 CLEANUP ÚSPĚŠNĚ DOKONČEN!")
        print(f"📋 Změny:")
        print(f"   ❌ Odstraněn sloupec 'username'")
        print(f"   ❌ Odstraněn sloupec 'jmeno'")
        print(f"   ✅ Email nastaven jako UNIQUE")
        print(f"   ✅ Zachována jednoduchá struktura")
        
        return True
        
    except Exception as e:
        print(f"❌ Chyba při ověření: {e}")
        return False

def main():
    """Hlavní funkce cleanup"""
    
    print("🧹 CLEANUP USERS TABULKY - ZJEDNODUŠENÍ")
    print("=" * 60)
    
    with app.app_context():
        # Kontrola současného stavu
        check_result = check_current_state()
        
        if not check_result[0]:
            print("\n❌ Nelze pokračovat - chyba při kontrole stavu")
            return False
        
        can_continue, has_username, has_jmeno = check_result
        
        print(f"\n✅ Databáze je připravena k cleanup")
        print(f"⚠️  POZOR: Budou odstraněny sloupce z users tabulky!")
        
        response = input("\nPokračovat v cleanup? (y/N): ")
        if response.lower() != 'y':
            print("Cleanup zrušen uživatelem")
            return False
        
        # Prováděj cleanup krok za krokem
        steps = [
            lambda: step1_drop_username_column(has_username),
            lambda: step2_drop_jmeno_column(has_jmeno),
            step3_add_email_unique_constraint,
            step4_cleanup_poznamka_column
        ]
        
        for i, step_func in enumerate(steps, 1):
            print(f"\n▶️  Provádím krok {i}/{len(steps)}...")
            
            if not step_func():
                print(f"\n❌ Krok {i} selhal! Ukončuji cleanup.")
                return False
            
            print(f"✅ Krok {i} dokončen")
        
        # Finální ověření
        success = final_verification()
        
        return success

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)