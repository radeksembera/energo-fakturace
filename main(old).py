# -*- coding: utf-8 -*-
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import os
import pandas as pd
from datetime import datetime
from pathlib import Path  
from file_helpers import get_faktury_path, get_faktura_filenames, check_faktury_exist

import sys
import os
# Nastav UTF-8 kódování
os.environ['PYTHONIOENCODING'] = 'utf-8'



# PŘIDEJ TADY:
def safe_excel_string(value, zfill_length=None):
    """Bezpečně převede Excel hodnotu na string s ošetřením vedoucích nul"""
    if pd.isna(value) or value == "":
        return ""
    if isinstance(value, (int, float)) and zfill_length:
        return f"{int(value):0{zfill_length}d}"
    return str(value).strip()


from models import db, User, CenaDistribuce, CenaDodavatel, InfoDodavatele, InfoVystavovatele, InfoOdberatele, Stredisko, OdberneMisto, VypocetOM, Odecet, ImportOdectu, ZalohovaFaktura, Faktura, ObdobiFakturace, UserStredisko
from datetime import datetime
from fakturace_routes import fakturace_bp
from odecty import odecty_bp
from print import print_bp

from session_helpers import (
    get_session_obdobi, 
    set_session_obdobi, 
    handle_obdobi_selection,
    handle_obdobi_from_rok_mesic
)

# lokal start
from dotenv import load_dotenv
# lokal end

if os.path.exists('.env'):
    load_dotenv()


app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "tajny_klic")
app.register_blueprint(fakturace_bp, url_prefix="/strediska")
app.register_blueprint(odecty_bp, url_prefix="/strediska")
app.register_blueprint(print_bp, url_prefix="/faktury")


# app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("DATABASE_URL")
# lokal start
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("SQLALCHEMY_DATABASE_URI")
# lokal end

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

# Pokud spouštíš lokálně, můžeš použít create_all (na serveru to nedělej!)
with app.app_context():
    db.create_all()

@app.route("/")
def index():
    if not session.get("user_id"):
        return redirect("/login")
    return redirect("/strediska")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        user = db.session.query(User).filter(User.email == email).first()

        print(f"DEBUG: User found: {user}")
        if user:
            print(f"DEBUG: User email: {user.email}")
            print(f"DEBUG: User is_admin: {user.is_admin}")
            print(f"DEBUG: User is_active: {user.is_active}")

        if user and check_password_hash(user.password_hash, password):
            if not user.is_active:
                return render_template("login.html", error="Váš účet byl deaktivován. Kontaktujte administrátora.")
            
            session["user_id"] = user.id
            session["email"] = user.email
            session["is_admin"] = user.is_admin  # ✅ TOTO MUSÍ BÝT TADY!
            
            print(f"DEBUG: Session after login: {dict(session)}")
            return redirect("/strediska")
        return render_template("login.html", error="Neplatné přihlášení.")

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# V main.py - oprava route strediska

@app.route("/strediska")
def strediska():
    print(f"Session: {dict(session)}")  # Debug print
    if not session.get("user_id"):
        return redirect("/login")
    
    user_id = session["user_id"]
    user = User.query.get(user_id)
    
    # Admin vidí všechna střediska
    if user and user.is_admin:
        strediska = Stredisko.query.all()
        print(f"Admin vidi {len(strediska)} stredisek")
    else:
        # ✅ OPRAVA: Kombinuj oba přístupy - původní + nový systém
        # 1. Střediska podle původního systému (user_id)
        strediska_puvodni = Stredisko.query.filter_by(user_id=user_id).all()
        
        # 2. Střediska podle nového systému (UserStredisko tabulka)
        strediska_nova = db.session.query(Stredisko)\
            .join(UserStredisko)\
            .filter(UserStredisko.user_id == user_id)\
            .filter(UserStredisko.pravo_cteni == True)\
            .all()
        
        # 3. Spojit obě množiny (bez duplicit)
        strediska_ids = set()
        strediska = []
        
        # Přidej původní střediska
        for s in strediska_puvodni:
            if s.id not in strediska_ids:
                strediska.append(s)
                strediska_ids.add(s.id)
        
        # Přidej nová střediska
        for s in strediska_nova:
            if s.id not in strediska_ids:
                strediska.append(s)
                strediska_ids.add(s.id)
        
        # Seřaď podle názvu
        strediska = sorted(strediska, key=lambda x: x.nazev_strediska)
        
        print(f"Uzivatel {user_id} vidi {len(strediska)} stredisek")
        print(f"   - Puvodni system: {len(strediska_puvodni)}")
        print(f"   - Novy system: {len(strediska_nova)}")
    
    return render_template("prehled_stredisek.html", strediska=strediska)

@app.route("/strediska/<int:stredisko_id>")
def spravovat_stredisko(stredisko_id):
    if not session.get("user_id"):
        return redirect("/login")

    # ✅ NOVÁ KONTROLA PŘÍSTUPU
    if not check_stredisko_access(stredisko_id, 'read'):
        flash("❌ Nemáte oprávnění k tomuto středisku.")
        return redirect("/strediska")

    stredisko = Stredisko.query.get_or_404(stredisko_id)
    return render_template("sprava_strediska.html", stredisko=stredisko)


@app.route("/strediska/<int:stredisko_id>/odberna_mista", methods=["GET", "POST"])
def prehled_odbernych_mist(stredisko_id):
    if not session.get("user_id"):
        return redirect("/login")

    # ✅ KONTROLA PŘÍSTUPU
    write_access = check_stredisko_access(stredisko_id, 'write')
    if not check_stredisko_access(stredisko_id, 'read'):
        flash("❌ Nemáte oprávnění k tomuto středisku.")
        return redirect("/strediska")

    stredisko = Stredisko.query.get_or_404(stredisko_id)

    # ✅ POUZE S WRITE OPRÁVNĚNÍM MŮŽE PŘIDÁVAT
    if request.method == "POST":
        if not write_access:
            flash("❌ Nemáte oprávnění upravovat toto středisko.")
            return redirect(url_for('prehled_odbernych_mist', stredisko_id=stredisko_id))
        
        # Zbytek kódu zůstává stejný...
        nove_om = OdberneMisto(
            stredisko_id=stredisko_id,
            cislo_om=request.form["cislo_om"],
            ean_om=request.form["ean_om"],
            nazev_om=request.form["nazev_om"],
            distribucni_sazba_om=request.form["distribucni_sazba_om"],
            kategorie_jistice_om=request.form["kategorie_jistice_om"],
            hodnota_jistice_om=request.form["hodnota_jistice_om"],
            poznamka_om=request.form["poznamka_om"]
        )
        db.session.add(nove_om)
        db.session.commit()
        return redirect(url_for('prehled_odbernych_mist', stredisko_id=stredisko_id))

    odberna_mista = OdberneMisto.query.filter_by(stredisko_id=stredisko_id).all()
    return render_template("prehled_odbernych_mist.html", 
                          stredisko=stredisko, 
                          odberna_mista=odberna_mista,
                          write_access=write_access)


def vytvor_vychozi_obdobi(stredisko_id):
    """Vytvori vychozi obdobi pro nove stredisko - od 1/2025 do 12/2026"""
    
    # FIXED - vytvor obdobi od 1/2025 do 12/2026
    for rok in range(2025, 2027):  # 2025 a 2026
        for mesic in range(1, 13):  # mesice 1-12
            # Zkontroluj, jestli obdobi uz neexistuje
            existujici = ObdobiFakturace.query.filter_by(
                stredisko_id=stredisko_id,
                rok=rok,
                mesic=mesic
            ).first()
            
            if not existujici:
                obdobi = ObdobiFakturace(
                    stredisko_id=stredisko_id,
                    rok=rok,
                    mesic=mesic
                )
                db.session.add(obdobi)
    
    print(f"[OK] Vytvorena vychozi obdobi 1/2025 - 12/2026 pro stredisko {stredisko_id}")

# NOVA FUNKCE - rozsireni obdobi pokud je potreba
def rozsir_obdobi_pokud_potreba(stredisko_id, cilovy_rok=None):
    """Rozsiri obdobi pokud je potreba pro starsi/novejsi roky"""
    
    if not cilovy_rok:
        from datetime import datetime
        cilovy_rok = datetime.now().year
    
    # Najdi nejstarsi a nejnovejsi existujici obdobi
    nejstarsi = ObdobiFakturace.query.filter_by(stredisko_id=stredisko_id)\
        .order_by(ObdobiFakturace.rok.asc(), ObdobiFakturace.mesic.asc()).first()
    
    nejnovejsi = ObdobiFakturace.query.filter_by(stredisko_id=stredisko_id)\
        .order_by(ObdobiFakturace.rok.desc(), ObdobiFakturace.mesic.desc()).first()
    
    if not nejstarsi or not nejnovejsi:
        return  # Zadna obdobi neexistuji
    
def vytvor_vychozi_obdobi(stredisko_id):
    """Vytvori vychozi obdobi pro nove stredisko - od 1/2025 do 12/2026"""
    
    # FIXED - vytvor obdobi od 1/2025 do 12/2026
    for rok in range(2025, 2027):  # 2025 a 2026
        for mesic in range(1, 13):  # mesice 1-12
            # Zkontroluj, jestli obdobi uz neexistuje
            existujici = ObdobiFakturace.query.filter_by(
                stredisko_id=stredisko_id,
                rok=rok,
                mesic=mesic
            ).first()
            
            if not existujici:
                obdobi = ObdobiFakturace(
                    stredisko_id=stredisko_id,
                    rok=rok,
                    mesic=mesic
                )
                db.session.add(obdobi)
    
    print(f"[OK] Vytvorena vychozi obdobi 1/2025 - 12/2026 pro stredisko {stredisko_id}")

# NOVA FUNKCE - rozsireni obdobi pokud je potreba
def rozsir_obdobi_pokud_potreba(stredisko_id, cilovy_rok=None):
    """Rozsiri obdobi pokud je potreba pro starsi/novejsi roky"""
    
    if not cilovy_rok:
        from datetime import datetime
        cilovy_rok = datetime.now().year
    
    # Najdi nejstarsi a nejnovejsi existujici obdobi
    nejstarsi = ObdobiFakturace.query.filter_by(stredisko_id=stredisko_id)\
        .order_by(ObdobiFakturace.rok.asc(), ObdobiFakturace.mesic.asc()).first()
    
    nejnovejsi = ObdobiFakturace.query.filter_by(stredisko_id=stredisko_id)\
        .order_by(ObdobiFakturace.rok.desc(), ObdobiFakturace.mesic.desc()).first()
    
    if not nejstarsi or not nejnovejsi:
        return  # Zadna obdobi neexistuji
    
    # Rozšiř do minulosti pokud je potřeba
    if cilovy_rok < nejstarsi.rok:
        for rok in range(cilovy_rok, nejstarsi.rok):
            for mesic in range(1, 13):
                existujici = ObdobiFakturace.query.filter_by(
                    stredisko_id=stredisko_id, rok=rok, mesic=mesic
                ).first()
                if not existujici:
                    obdobi = ObdobiFakturace(
                        stredisko_id=stredisko_id, rok=rok, mesic=mesic
                    )
                    db.session.add(obdobi)
        print(f"[OK] Rozsirena obdobi do minulosti do roku {cilovy_rok}")
    
    # Rozšiř do budoucnosti pokud je potřeba  
    if cilovy_rok > nejnovejsi.rok:
        for rok in range(nejnovejsi.rok + 1, cilovy_rok + 1):
            for mesic in range(1, 13):
                existujici = ObdobiFakturace.query.filter_by(
                    stredisko_id=stredisko_id, rok=rok, mesic=mesic
                ).first()
                if not existujici:
                    obdobi = ObdobiFakturace(
                        stredisko_id=stredisko_id, rok=rok, mesic=mesic
                    )
                    db.session.add(obdobi)
        print(f"[OK] Rozsirena obdobi do budoucnosti do roku {cilovy_rok}")
    
    db.session.commit()

# V main.py - oprava route pridat_stredisko

@app.route("/strediska/pridat", methods=["GET", "POST"])
def pridat_stredisko():
    if not session.get("user_id"):
        return redirect("/login")

    if request.method == "POST":
        nazev = request.form["nazev"]
        adresa = request.form["adresa"]
        misto = request.form["misto"]
        stredisko_kod = request.form["stredisko"]
        email = request.form["stredisko_mail"]
        distribuce = request.form["distribuce"]
        poznamka = request.form["poznamka"]

        # Vytvoř nové středisko
        nove_stredisko = Stredisko(
            user_id=session["user_id"],  # ✅ Zachováno pro kompatibilitu
            nazev_strediska=nazev,
            adresa=adresa,
            misto=misto,
            stredisko=stredisko_kod,
            stredisko_mail=email,
            distribuce=distribuce,
            poznamka=poznamka,
            role="uživatel"
        )
        db.session.add(nove_stredisko)
        db.session.flush()  # ✅ Získej ID střediska před commit
        
        # ✅ NOVÉ: Přidej uživatele do UserStredisko s plnými právy
        user_stredisko = UserStredisko(
            user_id=session["user_id"],
            stredisko_id=nove_stredisko.id,
            pravo_cteni=True,
            pravo_upravy=True,
            pravo_spravce=True,  # Tvůrce má práva správce
            prideleno_kdy=datetime.utcnow(),
            pridelil_admin_id=session["user_id"]  # Sám sobě
        )
        db.session.add(user_stredisko)
        
        # Automatické vytvoření všech typů období
        vytvor_vychozi_obdobi(nove_stredisko.id)
        
        db.session.commit()
        
        flash(f"[OK] Stredisko bylo vytvoreno a automaticky byla pridana vsechna obdobi.")
        return redirect("/strediska")

    return render_template("pridat_stredisko.html")

# ================ CENY DISTRIBUCE (podle roku) ================
@app.route("/strediska/<int:stredisko_id>/ceny_distribuce")
def ceny_distribuce(stredisko_id):
    if not session.get("user_id"):
        return redirect("/login")

    stredisko = Stredisko.query.get_or_404(stredisko_id)
    if stredisko.user_id != session["user_id"]:
        return "Nepovolený přístup", 403

    # Získej zvolený rok z query parametrů nebo nastav na aktuální rok
    zvoleny_rok = request.args.get("rok", type=int, default=datetime.now().year)
    
    # Najdi všechny roky, pro které máme ceny distribuce
    dostupne_roky_query = db.session.query(CenaDistribuce.rok)\
        .filter_by(stredisko_id=stredisko_id)\
        .filter(CenaDistribuce.rok.isnot(None))\
        .distinct()\
        .order_by(CenaDistribuce.rok.desc())\
        .all()
    
    dostupne_roky = [r[0] for r in dostupne_roky_query] if dostupne_roky_query else []
    
    # Načti ceny pro zvolený rok
    ceny = CenaDistribuce.query.filter_by(
        stredisko_id=stredisko_id,
        rok=zvoleny_rok
    ).all()
    
    return render_template("ceny_distribuce.html", 
                          ceny_distribuce=ceny, 
                          stredisko_id=stredisko_id,
                          stredisko=stredisko,
                          zvoleny_rok=zvoleny_rok,
                          dostupne_roky=dostupne_roky)

@app.route("/strediska/<int:stredisko_id>/nahrat_ceny_distribuce", methods=["POST"])
def nahrat_ceny_distribuce(stredisko_id):
    file = request.files.get("xlsx_file")

    # Získej rok z formuláře
    rok = request.form.get("rok", type=int)
    if not rok:
        rok = datetime.now().year

    if not file:
        flash("Nebyl vybrán žádný soubor.")
        return redirect(url_for("ceny_distribuce", stredisko_id=stredisko_id, rok=rok))

    try:
        df = pd.read_excel(file)

        # Smaž pouze záznamy pro daný rok a středisko
        CenaDistribuce.query.filter_by(
            stredisko_id=stredisko_id,
            rok=rok
        ).delete()

        for _, row in df.iterrows():
            zaznam = CenaDistribuce(
                stredisko_id=stredisko_id,
                rok=rok,  # Použij rok přímo
                distribuce=row["distribuce"],
                sazba=row["sazba"],
                jistic=row["jistic"],
                platba_za_jistic=row["platba_za_jistic"],
                platba_za_distribuci_vt=row["platba_za_distribuci_vt"],
                platba_za_distribuci_nt=row["platba_za_distribuci_nt"],
                systemove_sluzby=row["systemove_sluzby"],
                poze_dle_jistice=row["poze_dle_jistice"],
                poze_dle_spotreby=row["poze_dle_spotreby"],
                nesitova_infrastruktura=row["nesitova_infrastruktura"],
                dan_z_elektriny=row["dan_z_elektriny"]
            )
            db.session.add(zaznam)

        db.session.commit()
        flash(f"✅ Import cen distribuce pro rok {rok} proběhl v pořádku.")
    except Exception as e:
        flash(f"❌ Chyba při importu: {e}")

    return redirect(url_for("ceny_distribuce", stredisko_id=stredisko_id, rok=rok))

@app.route("/strediska/<int:stredisko_id>/smazat_ceny_distribuce", methods=["POST"])
def smazat_ceny_distribuce(stredisko_id):
    if not session.get("user_id"):
        return redirect("/login")

    # Získej rok z formuláře
    rok = request.form.get("rok", type=int)

    try:
        if rok:
            # Smaž ceny pro konkrétní rok
            smazano = CenaDistribuce.query.filter_by(
                stredisko_id=stredisko_id,
                rok=rok
            ).delete()
            
            if smazano > 0:
                flash(f"✅ Ceny distribuce pro rok {rok} byly úspěšně smazány ({smazano} záznamů).")
            else:
                flash(f"⚠️ Pro rok {rok} nebyly nalezeny žádné ceny distribuce.")
        else:
            # Smaž všechny ceny distribuce pro středisko
            smazano = CenaDistribuce.query.filter_by(stredisko_id=stredisko_id).delete()
            flash(f"✅ Všechny ceny distribuce byly úspěšně smazány ({smazano} záznamů).")

        db.session.commit()
    except Exception as e:
        flash(f"❌ Chyba při mazání záznamů: {e}")

    return redirect(url_for("ceny_distribuce", stredisko_id=stredisko_id, rok=rok))

# ================ CENY DODAVATELE (podle měsíců od 1/2025 přes období) ================
# ================ CENY DODAVATELE (zjednodušené - přímo rok/měsíc) ================
# V main.py - oprava route ceny_dodavatele

@app.route("/strediska/<int:stredisko_id>/ceny_dodavatele")
def ceny_dodavatele(stredisko_id):
    if not session.get("user_id"):
        return redirect("/login")

    stredisko = Stredisko.query.get_or_404(stredisko_id)
    if stredisko.user_id != session["user_id"]:
        return "Nepovolený přístup", 403

    # ✅ OPRAVA: Získej rok/měsíc z URL parametrů
    url_rok = request.args.get("rok", type=int)
    url_mesic = request.args.get("mesic", type=int)
    
    if url_rok and url_mesic:
        # Pokud jsou v URL parametrech rok/měsíc, najdi nebo vytvoř období
        vybrane_obdobi = ObdobiFakturace.query.filter_by(
            stredisko_id=stredisko_id,
            rok=url_rok,
            mesic=url_mesic
        ).first()
        
        if not vybrane_obdobi:
            # ✅ OPRAVA: Pokud období neexistuje, vytvoř ho
            vybrane_obdobi = ObdobiFakturace(
                stredisko_id=stredisko_id,
                rok=url_rok,
                mesic=url_mesic
            )
            db.session.add(vybrane_obdobi)
            db.session.commit()
            flash(f"✅ Vytvořeno nové období {url_rok}/{url_mesic:02d}")
        
        # ✅ OPRAVA: Ulož vybrané období do session
        set_session_obdobi(stredisko_id, vybrane_obdobi.id)
        zvoleny_rok = vybrane_obdobi.rok
        zvoleny_mesic = vybrane_obdobi.mesic
        
    else:
        # ✅ Pokud nejsou URL parametry, použij session
        vybrane_obdobi = get_session_obdobi(stredisko_id)
        if vybrane_obdobi:
            zvoleny_rok = vybrane_obdobi.rok
            zvoleny_mesic = vybrane_obdobi.mesic
        else:
            # Fallback na 2025/1
            zvoleny_rok = 2025
            zvoleny_mesic = 1
    
    # Načti dostupná období
    dostupna_obdobi_query = db.session.query(ObdobiFakturace.rok, ObdobiFakturace.mesic)\
        .join(CenaDodavatel, CenaDodavatel.obdobi_id == ObdobiFakturace.id)\
        .filter(ObdobiFakturace.stredisko_id == stredisko_id)\
        .distinct()\
        .order_by(ObdobiFakturace.rok.desc(), ObdobiFakturace.mesic.desc())\
        .all()
    
    dostupna_obdobi = [f"{r}/{m:02d}" for r, m in dostupna_obdobi_query]

    # Načti ceny pro vybrané období
    ceny = []
    if vybrane_obdobi:
        ceny = CenaDodavatel.query.filter_by(obdobi_id=vybrane_obdobi.id).all()
    
    return render_template("ceny_dodavatele.html", 
                          ceny_dodavatele=ceny, 
                          stredisko_id=stredisko_id,
                          stredisko=stredisko,
                          zvoleny_rok=zvoleny_rok,
                          zvoleny_mesic=zvoleny_mesic,
                          dostupna_obdobi=dostupna_obdobi,
                          vybrane_obdobi=vybrane_obdobi)

@app.route("/strediska/<int:stredisko_id>/nahrat_ceny_dodavatele", methods=["POST"])
def nahrat_ceny_dodavatele(stredisko_id):
    file = request.files.get("xlsx_file")
    
    # Získej rok a měsíc z formuláře
    rok = request.form.get("rok", type=int, default=2025)
    mesic = request.form.get("mesic", type=int, default=1)
    
    # Najdi období
    obdobi = ObdobiFakturace.query.filter_by(
        stredisko_id=stredisko_id,
        rok=rok,
        mesic=mesic
    ).first()
    
    if not obdobi:
        flash(f"❌ Období {rok}/{mesic:02d} neexistuje. Vytvořte jej nejprve.")
        return redirect(url_for("ceny_dodavatele", stredisko_id=stredisko_id, rok=rok, mesic=mesic))
    
    if not file:
        flash("Nebyl vybrán žádný soubor.")
        return redirect(url_for("ceny_dodavatele", stredisko_id=stredisko_id, rok=rok, mesic=mesic))

    try:
        df = pd.read_excel(file)

        # Smaž pouze záznamy pro dané období
        CenaDodavatel.query.filter_by(obdobi_id=obdobi.id).delete()

        for _, row in df.iterrows():
            zaznam = CenaDodavatel(
                stredisko_id=stredisko_id,
                obdobi_id=obdobi.id,
                distribuce=row["distribuce"],
                sazba=row["sazba"],
                jistic=row["jistic"],
                platba_za_elektrinu_vt=row["platba_za_elektrinu_vt"],
                platba_za_elektrinu_nt=row["platba_za_elektrinu_nt"],
                mesicni_plat=row["mesicni_plat"]
            )
            db.session.add(zaznam)

        db.session.commit()
        flash(f"✅ Import cen dodavatele pro {rok}/{mesic:02d} proběhl v pořádku.")
    except Exception as e:
        flash(f"❌ Chyba při importu: {e}")

    return redirect(url_for("ceny_dodavatele", stredisko_id=stredisko_id, rok=rok, mesic=mesic))

@app.route("/strediska/<int:stredisko_id>/smazat_ceny_dodavatele", methods=["POST"])
def smazat_ceny_dodavatele(stredisko_id):
    if not session.get("user_id"):
        return redirect("/login")

    # Získej rok a měsíc z formuláře
    rok = request.form.get("rok", type=int)
    mesic = request.form.get("mesic", type=int)
    
    try:
        if rok and mesic:
            # Najdi období a smaž ceny pro něj
            obdobi = ObdobiFakturace.query.filter_by(
                stredisko_id=stredisko_id,
                rok=rok,
                mesic=mesic
            ).first()
            
            if obdobi:
                smazano = CenaDodavatel.query.filter_by(obdobi_id=obdobi.id).delete()
                flash(f"✅ Ceny dodavatele pro {rok}/{mesic:02d} byly úspěšně smazány ({smazano} záznamů).")
            else:
                flash(f"❌ Období {rok}/{mesic:02d} neexistuje.")
        else:
            # Smaž všechny ceny dodavatele pro středisko
            smazano = CenaDodavatel.query.filter_by(stredisko_id=stredisko_id).delete()
            flash(f"✅ Všechny ceny dodavatele byly úspěšně smazány ({smazano} záznamů).")
            
        db.session.commit()
    except Exception as e:
        flash(f"❌ Chyba při mazání záznamů: {e}")

    return redirect(url_for("ceny_dodavatele", stredisko_id=stredisko_id, rok=rok, mesic=mesic))

@app.route("/strediska/<int:stredisko_id>/nahrat_odberna_mista", methods=["POST"])
def nahrat_odberna_mista(stredisko_id):
    if not session.get("user_id"):
        return redirect("/login")

    stredisko = Stredisko.query.get_or_404(stredisko_id)
    if stredisko.user_id != session["user_id"]:
        return "Nepovolený přístup", 403

    file = request.files.get("xlsx_file")
    if not file:
        flash("Nebyl vybrán žádný soubor.")
        return redirect(url_for("prehled_odbernych_mist", stredisko_id=stredisko_id))

    try:
        df = pd.read_excel(file)
        
        # Získej existující čísla OM pro kontrolu duplicit
        existujici_om = {om.cislo_om for om in OdberneMisto.query.filter_by(stredisko_id=stredisko_id).all()}
        
        uspesne_importy = 0
        preskoceno = 0
        chyby = []

        for index, row in df.iterrows():
            try:
                # Bezpečné načtení hodnot
                cislo_om = safe_excel_string(row["cislo_om"], 7)  # 7 číslic s vedoucími nulami
                
                # Kontrola duplicit
                if cislo_om in existujici_om:
                    preskoceno += 1
                    continue
                
                # Vytvoř nové odběrné místo
                nove_om = OdberneMisto(
                    stredisko_id=stredisko_id,
                    cislo_om=cislo_om,
                    ean_om=safe_excel_string(row.get("ean_om")),
                    nazev_om=safe_excel_string(row.get("nazev_om")),
                    distribucni_sazba_om=safe_excel_string(row.get("distribucni_sazba_om")),
                    kategorie_jistice_om=safe_excel_string(row.get("kategorie_jistice_om")),
                    hodnota_jistice_om=safe_excel_string(row.get("hodnota_jistice_om")),
                    poznamka_om=safe_excel_string(row.get("poznamka_om"))
                )
                
                db.session.add(nove_om)
                existujici_om.add(cislo_om)
                uspesne_importy += 1

            except Exception as e:
                chyba_msg = f"Řádek {index + 2}: {str(e)}"
                chyby.append(chyba_msg)

        db.session.commit()
        
        # Zprávy o výsledku
        if uspesne_importy > 0:
            flash(f"✅ Úspěšně importováno {uspesne_importy} odběrných míst.")
        
        if preskoceno > 0:
            flash(f"⚠️ Přeskočeno {preskoceno} duplicitních odběrných míst.")
        
        if chyby:
            for chyba in chyby[:5]:  # Zobraz max 5 chyb
                flash(f"❌ {chyba}")
            if len(chyby) > 5:
                flash(f"❌ ... a dalších {len(chyby)-5} chyb")

    except Exception as e:
        flash(f"❌ Chyba při importu: {e}")

    return redirect(url_for("prehled_odbernych_mist", stredisko_id=stredisko_id))

@app.template_filter('safe_sum')
def safe_sum_filter(values, attribute=None):
    """Bezpečný součet hodnot, který ignoruje None"""
    if attribute:
        # Pokud je zadán atribut, extrahujeme hodnoty z objektů
        numeric_values = []
        for item in values:
            if hasattr(item, attribute):
                val = getattr(item, attribute)
                if val is not None:
                    numeric_values.append(float(val))
        return sum(numeric_values)
    else:
        # Pokud není atribut, sčítáme přímo hodnoty
        numeric_values = [float(v) for v in values if v is not None]
        return sum(numeric_values)

from flask import jsonify

@app.route("/strediska/<int:stredisko_id>/upravit_odberne_misto", methods=["POST"])
def upravit_odberne_misto(stredisko_id):
    if not session.get("user_id"):
        return jsonify({"status": "error", "message": "Nepovolený přístup"}), 403

    stredisko = Stredisko.query.get_or_404(stredisko_id)
    if stredisko.user_id != session["user_id"]:
        return jsonify({"status": "error", "message": "Nepovolený přístup"}), 403

    try:
        # Získej parametry z X-editable
        om_id = request.form.get('pk')  # primary key
        field_name = request.form.get('name')  # název pole
        new_value = request.form.get('value')  # nová hodnota

        # Najdi odběrné místo
        om = OdberneMisto.query.filter_by(id=om_id, stredisko_id=stredisko_id).first()
        if not om:
            return jsonify({"status": "error", "message": "Odběrné místo nebylo nalezeno"}), 404

        # Aktualizuj pole
        if hasattr(om, field_name):
            setattr(om, field_name, new_value)
            db.session.commit()
            return jsonify({"status": "success", "message": f"Pole {field_name} bylo úspěšně aktualizováno"})
        else:
            return jsonify({"status": "error", "message": f"Neznámé pole: {field_name}"}), 400

    except Exception as e:
        return jsonify({"status": "error", "message": f"Chyba při ukládání: {str(e)}"}), 500


@app.route("/strediska/<int:stredisko_id>/smazat_odberne_misto", methods=["POST"])
def smazat_odberne_misto(stredisko_id):
    if not session.get("user_id"):
        return jsonify({"status": "error", "message": "Nepovolený přístup"}), 403

    stredisko = Stredisko.query.get_or_404(stredisko_id)
    if stredisko.user_id != session["user_id"]:
        return jsonify({"status": "error", "message": "Nepovolený přístup"}), 403

    try:
        om_id = request.form.get('om_id')
        
        # Najdi a smaž odběrné místo
        om = OdberneMisto.query.filter_by(id=om_id, stredisko_id=stredisko_id).first()
        if not om:
            return jsonify({"status": "error", "message": "Odběrné místo nebylo nalezeno"}), 404

        # Smaž všechny související výpočty
        VypocetOM.query.filter_by(odberne_misto_id=om.id).delete()
        
        # Smaž odběrné místo
        db.session.delete(om)
        db.session.commit()
        
        return jsonify({"status": "success", "message": f"Odběrné místo {om.cislo_om} bylo úspěšně smazáno"})

    except Exception as e:
        return jsonify({"status": "error", "message": f"Chyba při mazání: {str(e)}"}), 500
    
@app.route("/strediska/<int:stredisko_id>/upravit", methods=["POST"])
def upravit_stredisko(stredisko_id):
    if not session.get("user_id"):
        return redirect("/login")

    stredisko = Stredisko.query.get_or_404(stredisko_id)
    if stredisko.user_id != session["user_id"]:
        return "Nepovolený přístup", 403

    try:
        # Aktualizuj data střediska
        stredisko.nazev_strediska = request.form.get("nazev_strediska", "")
        stredisko.stredisko = request.form.get("stredisko_kod", "")
        stredisko.adresa = request.form.get("adresa", "")
        stredisko.misto = request.form.get("misto", "")
        stredisko.stredisko_mail = request.form.get("stredisko_mail", "")
        stredisko.distribuce = request.form.get("distribuce", "")
        stredisko.poznamka = request.form.get("poznamka", "")

        db.session.commit()
        flash("✅ Informace o středisku byly úspěšně aktualizovány.")
        
    except Exception as e:
        db.session.rollback()
        flash(f"❌ Chyba při ukládání: {str(e)}")

    return redirect(url_for("spravovat_stredisko", stredisko_id=stredisko_id))

def check_stredisko_access(stredisko_id, required_permission='read'):
    """
    Zkontroluje, jestli má uživatel přístup ke středisku
    required_permission: 'read', 'write', 'admin'
    """
    if not session.get("user_id"):
        return False
    
    user_id = session["user_id"]
    
    # Admin má přístup všude
    user = User.query.get(user_id)
    if user and user.is_admin:
        return True
    
    # Zkontroluj přístup přes UserStredisko tabulku
    access = UserStredisko.query.filter_by(
        user_id=user_id,
        stredisko_id=stredisko_id
    ).first()
    
    if not access:
        return False
    
    # Zkontroluj typ oprávnění
    if required_permission == 'read':
        return access.pravo_cteni
    elif required_permission == 'write':
        return access.pravo_upravy
    elif required_permission == 'admin':
        return access.pravo_spravce
    
    return False


# Funkce pro kontrolu admin přístupu
def admin_required(f):
    """Decorator pro kontrolu admin oprávnění"""
    def decorated_function(*args, **kwargs):
        if not session.get("user_id"):
            return redirect("/login")
        
        user = User.query.get(session["user_id"])
        if not user or not user.is_admin:
            flash("❌ Přístup povolen pouze administrátorům.")
            return redirect("/strediska")
        
        return f(*args, **kwargs)
    
    decorated_function.__name__ = f.__name__
    return decorated_function




# Přidej tyto funkce do main.py - jednoduché řešení

@app.route("/admin/users/<int:user_id>/edit", methods=["POST"])
def edit_user_simple(user_id):
    if not session.get("user_id"):
        return redirect("/login")
    
    user = User.query.get(session["user_id"])
    if not user or not user.is_admin:
        flash("❌ Přístup pouze pro administrátory.")
        return redirect("/strediska")

    target_user = User.query.get_or_404(user_id)
    
    # Aktualizuj data
    target_user.email = request.form.get("email", "").strip()
    new_password = request.form.get("password", "").strip()
    
    # ✅ PŘIDEJTE TENTO ŘÁDEK:
    target_user.is_active = 'is_active' in request.form
    
    if new_password:
        target_user.password_hash = generate_password_hash(new_password)
        flash(f"✅ Uživatel {target_user.email} byl aktualizován včetně nového hesla.")
    else:
        flash(f"✅ Uživatel {target_user.email} byl úspěšně aktualizován.")
    
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash(f"❌ Chyba při ukládání: {str(e)}")
    
    return redirect(url_for("admin_users"))

@app.route("/admin/users/<int:user_id>/reset-password", methods=["POST"])
def reset_password_simple(user_id):
    if not session.get("user_id"):
        return {"success": False, "message": "Nepovolený přístup"}, 403
    
    user = User.query.get(session["user_id"])
    # ✅ OPRAVA: kontrola přes is_admin sloupec
    if not user or not user.is_admin:
        return {"success": False, "message": "Nepovolený přístup"}, 403

    target_user = User.query.get_or_404(user_id)
    
    # Vygeneruj náhodné heslo
    import secrets
    import string
    alphabet = string.ascii_letters + string.digits + "!@#$%"
    new_password = ''.join(secrets.choice(alphabet) for i in range(10))
    
    target_user.password_hash = generate_password_hash(new_password)
    
    try:
        db.session.commit()
        return {
            "success": True, 
            "new_password": new_password,
            "message": f"Heslo pro {target_user.email} bylo resetováno"  # ✅ ZMĚNA: username → email
        }
    except Exception as e:
        db.session.rollback()
        return {"success": False, "message": str(e)}, 500

# Upravenou verzi původní admin_users funkce
@app.route("/admin/users", methods=["GET", "POST"])
def admin_users():
    if not session.get("user_id"):
        return redirect("/login")
    
    user = User.query.get(session["user_id"])
    # ✅ OPRAVA: kontrola přes is_admin sloupec
    if not user or not user.is_admin:
        flash("❌ Přístup pouze pro administrátory.")
        return redirect("/strediska")

    # Vytvoření nového uživatele
    if request.method == "POST":
        email = request.form.get("email", "").strip()  # ✅ ZMĚNA: username → email
        password = request.form.get("password", "").strip()
        
        if not email or not password:
            flash("❌ Email a heslo jsou povinné.")
            return redirect(url_for("admin_users"))
        
        # Zkontroluj duplicity
        if User.query.filter_by(email=email).first():  # ✅ ZMĚNA: username → email
            flash("❌ Uživatel s tímto emailem již existuje.")
            return redirect(url_for("admin_users"))
        
        # Vytvoř uživatele
        new_user = User(
            email=email,  # ✅ ZMĚNA: username → email
            password_hash=generate_password_hash(password)
        )
        
        try:
            db.session.add(new_user)
            db.session.commit()
            flash(f"✅ Uživatel {email} byl úspěšně vytvořen.")
        except Exception as e:
            db.session.rollback()
            flash(f"❌ Chyba při vytváření uživatele: {str(e)}")

    # Načti všechny uživatele
    users = User.query.order_by(User.id).all()
    
    return render_template("admin_users_simple.html", users=users)


# Přidejte do main.py nebo session_helpers.py

def get_unified_obdobi_list(stredisko_id=None):
    """
    Vrátí jednotný seznam období pro všechny selectboxy v aplikaci
    Seřazené chronologicky od nejstaršího po nejnovější (1/2025, 2/2025, ..., 12/2025)
    """
    if stredisko_id:
        # Pro konkrétní středisko - pouze existující období
        obdobi_query = ObdobiFakturace.query.filter_by(stredisko_id=stredisko_id)
    else:
        # Pro globální použití - všechna období ze všech středisek
        obdobi_query = ObdobiFakturace.query
    
    # Načti všechna existující období a seřaď je
    existujici_obdobi = obdobi_query.all()
    
    # Vytvoř set unikátních rok/měsíc kombinací
    unikatni_obdobi = set()
    for ob in existujici_obdobi:
        unikatni_obdobi.add((ob.rok, ob.mesic))
    
    # ✅ OPRAVA ŘAZENÍ: Seřaď chronologicky (nejstarší první)
    # Pro chronologické pořadí (1/2025 → 12/2025): odstraň reverse=True
    serazena_obdobi = sorted(list(unikatni_obdobi), key=lambda x: (x[0], x[1]))
    
    # Pokud chceš nejnovější první (12/2025 → 1/2025), přidej: reverse=True
    # serazena_obdobi = sorted(list(unikatni_obdobi), key=lambda x: (x[0], x[1]), reverse=True)
    
    # Vytvoř finální seznam
    obdobi_list = []
    for rok, mesic in serazena_obdobi:
        obdobi_list.append({
            'rok': rok,
            'mesic': mesic,
            'display': f"{rok}/{mesic:02d}",
            'value': f"{rok}-{mesic:02d}"
        })
    
    return obdobi_list

# V main.py přidejte template filter
@app.template_filter('get_obdobi')
def get_obdobi_filter(stredisko_id):
    """Template filter pro získání období"""
    return get_unified_obdobi_list(stredisko_id)

# A také template funkci
@app.template_global('get_unified_obdobi')
def get_unified_obdobi_template(stredisko_id):
    """Template global funkce"""
    return get_unified_obdobi_list(stredisko_id)


# V main.py - přidej tuto route

@app.route("/strediska/<int:stredisko_id>/kopirovat_ceny_dodavatele", methods=["POST"])
def kopirovat_ceny_dodavatele(stredisko_id):
    if not session.get("user_id"):
        return redirect("/login")

    stredisko = Stredisko.query.get_or_404(stredisko_id)
    if stredisko.user_id != session["user_id"]:
        return "Nepovolený přístup", 403

    try:
        # Získej cílový rok a měsíc z formuláře
        cilovy_rok = request.form.get("rok", type=int)
        cilovy_mesic = request.form.get("mesic", type=int)
        
        if not cilovy_rok or not cilovy_mesic:
            flash("❌ Chybí parametry roku nebo měsíce.")
            return redirect(url_for("ceny_dodavatele", stredisko_id=stredisko_id))

        # Najdi cílové období
        cilove_obdobi = ObdobiFakturace.query.filter_by(
            stredisko_id=stredisko_id,
            rok=cilovy_rok,
            mesic=cilovy_mesic
        ).first()
        
        if not cilove_obdobi:
            flash(f"❌ Cílové období {cilovy_rok}/{cilovy_mesic:02d} neexistuje.")
            return redirect(url_for("ceny_dodavatele", stredisko_id=stredisko_id))

        # Zkontroluj, jestli už cílové období nemá ceny
        existujici_ceny = CenaDodavatel.query.filter_by(obdobi_id=cilove_obdobi.id).count()
        if existujici_ceny > 0:
            flash(f"❌ Období {cilovy_rok}/{cilovy_mesic:02d} už obsahuje {existujici_ceny} cen. Nejprve je smažte.")
            return redirect(url_for("ceny_dodavatele", stredisko_id=stredisko_id, rok=cilovy_rok, mesic=cilovy_mesic))

        # Najdi předchozí období
        predchozi_rok = cilovy_rok
        predchozi_mesic = cilovy_mesic - 1
        
        if predchozi_mesic == 0:
            predchozi_mesic = 12
            predchozi_rok -= 1

        predchozi_obdobi = ObdobiFakturace.query.filter_by(
            stredisko_id=stredisko_id,
            rok=predchozi_rok,
            mesic=predchozi_mesic
        ).first()
        
        if not predchozi_obdobi:
            flash(f"❌ Předchozí období {predchozi_rok}/{predchozi_mesic:02d} neexistuje. Nelze kopírovat.")
            return redirect(url_for("ceny_dodavatele", stredisko_id=stredisko_id, rok=cilovy_rok, mesic=cilovy_mesic))

        # Načti ceny z předchozího období
        predchozi_ceny = CenaDodavatel.query.filter_by(obdobi_id=predchozi_obdobi.id).all()
        
        if not predchozi_ceny:
            flash(f"❌ Předchozí období {predchozi_rok}/{predchozi_mesic:02d} neobsahuje žádné ceny.")
            return redirect(url_for("ceny_dodavatele", stredisko_id=stredisko_id, rok=cilovy_rok, mesic=cilovy_mesic))

        # Kopíruj ceny do nového období
        zkopirowano = 0
        for puvodni_cena in predchozi_ceny:
            nova_cena = CenaDodavatel(
                stredisko_id=stredisko_id,
                obdobi_id=cilove_obdobi.id,  # ✅ Nové období
                distribuce=puvodni_cena.distribuce,
                sazba=puvodni_cena.sazba,
                jistic=puvodni_cena.jistic,
                platba_za_elektrinu_vt=puvodni_cena.platba_za_elektrinu_vt,
                platba_za_elektrinu_nt=puvodni_cena.platba_za_elektrinu_nt,
                mesicni_plat=puvodni_cena.mesicni_plat
            )
            db.session.add(nova_cena)
            zkopirowano += 1

        db.session.commit()
        
        flash(f"✅ Úspěšně zkopírováno {zkopirowano} cen z období {predchozi_rok}/{predchozi_mesic:02d} do {cilovy_rok}/{cilovy_mesic:02d}.")
        
        # Přesměruj na cílové období
        return redirect(url_for("ceny_dodavatele", stredisko_id=stredisko_id, rok=cilovy_rok, mesic=cilovy_mesic))

    except Exception as e:
        db.session.rollback()
        flash(f"❌ Chyba při kopírování cen: {str(e)}")
        return redirect(url_for("ceny_dodavatele", stredisko_id=stredisko_id))


# Přidej tuto route do main.py (např. za stávající route pro ceny dodavatele)

@app.route("/strediska/<int:stredisko_id>/hromadne_upravit_ceny_dodavatele", methods=["POST"])
def hromadne_upravit_ceny_dodavatele(stredisko_id):
    """Hromadná úprava všech cen dodavatele pro dané období"""
    if not session.get("user_id"):
        return redirect("/login")

    stredisko = Stredisko.query.get_or_404(stredisko_id)
    if stredisko.user_id != session["user_id"]:
        return "Nepovolený přístup", 403

    try:
        # Získej parametry z formuláře
        rok = request.form.get("rok", type=int)
        mesic = request.form.get("mesic", type=int)
        platba_za_elektrinu_vt = request.form.get("platba_za_elektrinu_vt", type=float)
        platba_za_elektrinu_nt = request.form.get("platba_za_elektrinu_nt", type=float)
        mesicni_plat = request.form.get("mesicni_plat", type=float)
        
        # Validace vstupních dat
        if not all([rok, mesic, platba_za_elektrinu_vt is not None, 
                   platba_za_elektrinu_nt is not None, mesicni_plat is not None]):
            flash("❌ Chybí povinné údaje pro úpravu cen.")
            return redirect(url_for("ceny_dodavatele", stredisko_id=stredisko_id, rok=rok, mesic=mesic))
        
        if any(x < 0 for x in [platba_za_elektrinu_vt, platba_za_elektrinu_nt, mesicni_plat]):
            flash("❌ Ceny nemohou být záporné.")
            return redirect(url_for("ceny_dodavatele", stredisko_id=stredisko_id, rok=rok, mesic=mesic))

        # Najdi období
        obdobi = ObdobiFakturace.query.filter_by(
            stredisko_id=stredisko_id,
            rok=rok,
            mesic=mesic
        ).first()
        
        if not obdobi:
            flash(f"❌ Období {rok}/{mesic:02d} neexistuje.")
            return redirect(url_for("ceny_dodavatele", stredisko_id=stredisko_id))

        # Spočítej kolik záznamů bude ovlivněno
        pocet_zaznamu = CenaDodavatel.query.filter_by(obdobi_id=obdobi.id).count()
        
        if pocet_zaznamu == 0:
            flash(f"❌ Pro období {rok}/{mesic:02d} nebyly nalezeny žádné ceny k úpravě.")
            return redirect(url_for("ceny_dodavatele", stredisko_id=stredisko_id, rok=rok, mesic=mesic))

        # Proveď hromadnou úpravu pomocí UPDATE query
        from sqlalchemy import text
        
        update_query = text("""
            UPDATE ceny_dodavatel 
            SET platba_za_elektrinu_vt = :vt,
                platba_za_elektrinu_nt = :nt,
                mesicni_plat = :plat
            WHERE obdobi_id = :obdobi_id
        """)
        
        result = db.session.execute(update_query, {
            'vt': platba_za_elektrinu_vt,
            'nt': platba_za_elektrinu_nt,
            'plat': mesicni_plat,
            'obdobi_id': obdobi.id
        })
        
        db.session.commit()
        
        # Informace o provedené změně
        updated_count = result.rowcount
        flash(f"✅ Úspěšně upraveno {updated_count} cenových záznamů pro období {rok}/{mesic:02d}.")
        flash(f"💰 Nové ceny: VT {platba_za_elektrinu_vt:.2f} Kč/MWh, NT {platba_za_elektrinu_nt:.2f} Kč/MWh, Měsíční plat {mesicni_plat:.2f} Kč/měsíc")
        
        # Log pro debug
        print(f"[UPDATE] Hromadna uprava cen: {updated_count} zaznamu pro stredisko {stredisko_id}, obdobi {rok}/{mesic:02d}")
        print(f"   - VT: {platba_za_elektrinu_vt} Kc/MWh")
        print(f"   - NT: {platba_za_elektrinu_nt} Kc/MWh") 
        print(f"   - Mesicni plat: {mesicni_plat} Kc/mesic")

    except ValueError as e:
        flash(f"❌ Neplatné hodnoty: {str(e)}")
        return redirect(url_for("ceny_dodavatele", stredisko_id=stredisko_id, rok=rok, mesic=mesic))
    except Exception as e:
        db.session.rollback()
        flash(f"❌ Chyba při úpravě cen: {str(e)}")
        print(f"[ERROR] Chyba pri hromadne uprave cen: {e}")
        return redirect(url_for("ceny_dodavatele", stredisko_id=stredisko_id, rok=rok, mesic=mesic))

    return redirect(url_for("ceny_dodavatele", stredisko_id=stredisko_id, rok=rok, mesic=mesic))



# ✅ PŘIDEJTE TENTO KÓD DO VAŠEHO PŮVODNÍHO main.py
# Vložte před "if __name__ == "__main__":" na konec souboru

import traceback

# Force error handling - PŘIDEJTE TYTO FUNKCE
@app.before_request
def log_request_info():
    print(f"🌐 Request: {request.method} {request.url}")
    print(f"🔑 Session: {dict(session)}")

@app.errorhandler(Exception)
def handle_exception(e):
    print("\n" + "="*80)
    print("❌ ZACHYCENA CHYBA V APLIKACI:")
    print("="*80)
    print(f"URL: {request.url}")
    print(f"Metoda: {request.method}")
    print(f"Typ chyby: {type(e).__name__}")
    print(f"Zpráva: {str(e)}")
    print("\nStack trace:")
    traceback.print_exc()
    print("="*80)
    
    # Zobrazení do browseru
    error_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>DEBUG - Chyba aplikace</title>
        <style>
            body {{ font-family: monospace; background: #f0f0f0; padding: 20px; }}
            .error {{ background: white; padding: 20px; border: 2px solid red; margin: 10px 0; }}
            pre {{ background: #f8f8f8; padding: 10px; border: 1px solid #ddd; overflow-x: auto; }}
        </style>
    </head>
    <body>
        <h1 style="color: red;">🚨 DEBUG - Zachycena chyba</h1>
        
        <div class="error">
            <h2>Základní info:</h2>
            <p><strong>URL:</strong> {request.url}</p>
            <p><strong>Metoda:</strong> {request.method}</p>
            <p><strong>Typ chyby:</strong> {type(e).__name__}</p>
        </div>
        
        <div class="error">
            <h2>Chybová zpráva:</h2>
            <pre>{str(e)}</pre>
        </div>
        
        <div class="error">
            <h2>Stack trace:</h2>
            <pre>{traceback.format_exc()}</pre>
        </div>
        
        <hr>
        <p><a href="/login">← Zpět na login</a> | <a href="/">Domů</a></p>
    </body>
    </html>
    """
    return error_html, 500


@app.route("/debug-test")
def debug_test():
    print("🧪 Debug test route voláno")
    return "<h1>✅ Debug test funguje!</h1><p><a href='/strediska'>Zkusit problematickou stránku</a></p>"



# V main.py na konci souboru změňte:
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    # Debug pouze lokálně
    debug_mode = os.environ.get("FLASK_ENV") == "development"
    app.run(host="0.0.0.0", port=port, debug=debug_mode)