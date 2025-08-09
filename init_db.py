#!/usr/bin/env python3
"""
Inicializační script pro vytvoření databáze a základního uživatele
"""

import os
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash
from main import app
from models import db, User

def init_database():
    """Vytvoří databázi a tabulky"""
    print("Inicializuji databazi...")
    
    # Načti environment proměnné
    load_dotenv()
    
    with app.app_context():
        try:
            # Vytvořit všechny tabulky
            db.create_all()
            print("OK - Databazove tabulky vytvoreny")
            
            # Zkontrolovat, zda už existuje admin uživatel
            admin = User.query.filter_by(email='admin@example.com').first()
            if not admin:
                # Vytvořit admin uživatele
                admin_user = User(
                    email='admin@example.com',
                    password_hash=generate_password_hash('admin123'),
                    is_admin=True,
                    is_active=True
                )
                db.session.add(admin_user)
                print("Admin uzivatel vytvoren:")
                print("   Email: admin@example.com")
                print("   Heslo: admin123")
            
            # Vytvořit testovacího běžného uživatele
            test_user = User.query.filter_by(email='user@example.com').first()
            if not test_user:
                test_user = User(
                    email='user@example.com',
                    password_hash=generate_password_hash('user123'),
                    is_admin=False,
                    is_active=True
                )
                db.session.add(test_user)
                print("Testovaci uzivatel vytvoren:")
                print("   Email: user@example.com")
                print("   Heslo: user123")
            
            # Uložit změny
            db.session.commit()
            print("OK - Databaze uspesne inicializovana!")
            
        except Exception as e:
            db.session.rollback()
            print(f"CHYBA - Pri inicializaci databaze: {e}")
            return False
    
    return True

if __name__ == "__main__":
    success = init_database()
    if success:
        print("")
        print("Nyni muzete spustit aplikaci pomoci: python main.py")
        print("A prihlasit se na: http://127.0.0.1:5000")
    else:
        print("")
        print("Inicializace se nezdarila!")
        exit(1)