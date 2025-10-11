from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from models import db, User, Stredisko, OdberneMisto, VypocetOM, Odečet, ObdobiFakturace, CenaDistribuce, CenaDodavatel, ImportOdečtu, ZalohovaFaktura, Faktura
from routes.auth import login_required
from utils.helpers import safe_excel_string
import pandas as pd
import os
from pathlib import Path
from datetime import datetime

strediska_bp = Blueprint("strediska", __name__, url_prefix="/strediska")

def check_stredisko_access(stredisko_id, required_permission='read'):
    """
    Kontroluje oprávnění uživatele k středisko
    required_permission: 'read', 'write'
    """
    if not session.get("user_id"):
        return False, redirect("/login")
    
    user_id = session["user_id"]
    user = User.query.get(user_id)
    
    # Admin má přístup ke všemu
    if user and user.is_admin:
        return True, None
    
    stredisko = Stredisko.query.get(stredisko_id)
    if not stredisko:
        return False, ("Středisko nenalezeno", 404)
    
    # Kontrola přístupu podle původního systému (user_id)
    if stredisko.user_id == user_id:
        return True, None
    
    # Kontrola přístupu podle nového systému (UserStredisko tabulka) - zatím neimplementováno
    
    return False, ("Nemáte oprávnění k tomuto středisku", 403)

@strediska_bp.route("/")
@login_required
def strediska():
    print(f"Session: {dict(session)}")
    
    user_id = session["user_id"]
    user = User.query.get(user_id)
    
    # Admin vidí všechna střediska
    if user and user.is_admin:
        strediska = Stredisko.query.all()
        print(f"Admin vidi {len(strediska)} stredisek")
    else:
        # Kombinuj oba přístupy - původní + nový systém
        # 1. Střediska podle původního systému (user_id)
        strediska_puvodni = Stredisko.query.filter_by(user_id=user_id).all()
        
        # 2. Střediska podle nového systému (UserStredisko tabulka) - zatím neimplementováno
        strediska_nova = []
        
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

@strediska_bp.route("/<int:stredisko_id>")
@login_required
def spravovat_stredisko(stredisko_id):
    has_access, error_response = check_stredisko_access(stredisko_id, 'read')
    if not has_access:
        flash("❌ Nemáte oprávnění k tomuto středisku.")
        return redirect("/strediska")

    stredisko = Stredisko.query.get_or_404(stredisko_id)
    return render_template("sprava_strediska.html", stredisko=stredisko)

@strediska_bp.route("/<int:stredisko_id>/upravit", methods=["POST"])
@login_required
def upravit_stredisko(stredisko_id):
    has_access, error_response = check_stredisko_access(stredisko_id, 'write')
    if not has_access:
        flash("❌ Nemáte oprávnění upravovat toto středisko.")
        return redirect(url_for("strediska.spravovat_stredisko", stredisko_id=stredisko_id))

    stredisko = Stredisko.query.get_or_404(stredisko_id)
    
    # Aktualizuj údaje střediska
    stredisko.nazev_strediska = request.form["nazev_strediska"]
    stredisko.stredisko = request.form["stredisko_kod"]
    stredisko.adresa = request.form["adresa"]
    stredisko.misto = request.form["misto"]
    stredisko.stredisko_mail = request.form["stredisko_mail"]
    stredisko.distribuce = request.form["distribuce"]
    stredisko.poznamka = request.form["poznamka"]
    
    db.session.commit()
    flash("✅ Středisko bylo úspěšně upraveno.")
    
    return redirect(url_for("strediska.spravovat_stredisko", stredisko_id=stredisko_id))

@strediska_bp.route("/<int:stredisko_id>/odberna_mista", methods=["GET", "POST"])
@login_required
def prehled_odbernych_mist(stredisko_id):
    has_access, error_response = check_stredisko_access(stredisko_id, 'read')
    if not has_access:
        flash("❌ Nemáte oprávnění k tomuto středisku.")
        return redirect("/strediska")
    
    has_write_access, _ = check_stredisko_access(stredisko_id, 'write')

    stredisko = Stredisko.query.get_or_404(stredisko_id)

    # Pouze s WRITE oprávněním může přidávat
    if request.method == "POST":
        if not has_write_access:
            flash("❌ Nemáte oprávnění upravovat toto středisko.")
            return redirect(url_for("strediska.prehled_odbernych_mist", stredisko_id=stredisko_id))

        cislo_om = request.form["cislo_om"]
        nazev_om = request.form["nazev_om"]
        distribucni_sazba_om = request.form.get("distribucni_sazba_om", "")
        kategorie_jistice_om = request.form.get("kategorie_jistice_om", "")
        hodnota_jistice_om = request.form.get("hodnota_jistice_om", "")
        ean_om = request.form.get("ean_om", "")
        poznamka_om = request.form.get("poznamka_om", "")

        if OdberneMisto.query.filter_by(stredisko_id=stredisko_id, cislo_om=cislo_om).first():
            flash(f"❌ Odběrné místo s kódem {cislo_om} již existuje!")
        else:
            nove_om = OdberneMisto(
                stredisko_id=stredisko_id,
                cislo_om=cislo_om,
                ean_om=ean_om,
                nazev_om=nazev_om,
                distribucni_sazba_om=distribucni_sazba_om,
                kategorie_jistice_om=kategorie_jistice_om,
                hodnota_jistice_om=hodnota_jistice_om,
                poznamka_om=poznamka_om
            )
            db.session.add(nove_om)
            db.session.commit()
            flash(f"✅ Odběrné místo {cislo_om} bylo přidáno.")
        
        return redirect(url_for("strediska.prehled_odbernych_mist", stredisko_id=stredisko_id))

    odberna_mista = OdberneMisto.query.filter_by(stredisko_id=stredisko_id).all()
    
    return render_template("prehled_odbernych_mist.html", 
                         stredisko=stredisko, 
                         odberna_mista=odberna_mista,
                         has_write_access=has_write_access)

@strediska_bp.route("/pridat", methods=["GET", "POST"])
@login_required
def pridat_stredisko():
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
            user_id=session["user_id"],
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
        db.session.commit()
        
        # Vytvoř období fakturace pro nové středisko (1/2025 až 12/2026)
        for rok in [2025, 2026]:
            for mesic in range(1, 13):
                obdobi = ObdobiFakturace(
                    stredisko_id=nove_stredisko.id,
                    rok=rok,
                    mesic=mesic
                )
                db.session.add(obdobi)
        
        db.session.commit()
        
        flash(f"✅ Středisko {nazev} bylo úspěšně vytvořeno s období fakturace 2025-2026.")
        return redirect(url_for("strediska.strediska"))

    return render_template("pridat_stredisko.html")

@strediska_bp.route("/<int:stredisko_id>/nahrat_odberna_mista", methods=["POST"])
@login_required
def nahrat_odberna_mista(stredisko_id):
    has_access, error_response = check_stredisko_access(stredisko_id, 'write')
    if not has_access:
        flash("❌ Nemáte oprávnění upravovat toto středisko.")
        return redirect(url_for("strediska.prehled_odbernych_mist", stredisko_id=stredisko_id))
    
    try:
        # Zkontroluj, zda byl soubor nahrán
        if 'file' not in request.files:
            flash("❌ Nebyl vybrán žádný soubor.")
            return redirect(url_for("strediska.prehled_odbernych_mist", stredisko_id=stredisko_id))
        
        file = request.files['file']
        if file.filename == '':
            flash("❌ Nebyl vybrán žádný soubor.")
            return redirect(url_for("strediska.prehled_odbernych_mist", stredisko_id=stredisko_id))
        
        # Zkontroluj příponu souboru
        if not file.filename.lower().endswith(('.xlsx', '.xls')):
            flash("❌ Podporované jsou pouze Excel soubory (.xlsx, .xls).")
            return redirect(url_for("strediska.prehled_odbernych_mist", stredisko_id=stredisko_id))
        
        # Načti Excel soubor
        try:
            df = pd.read_excel(file)
        except Exception as e:
            flash(f"❌ Chyba při čtení Excel souboru: {str(e)}")
            return redirect(url_for("strediska.prehled_odbernych_mist", stredisko_id=stredisko_id))
        
        # Zkontroluj požadované sloupce
        required_columns = ['cislo_om', 'ean_om', 'nazev_om', 'distribucni_sazba_om', 
                           'kategorie_jistice_om', 'hodnota_jistice_om', 'poznamka_om']
        missing_columns = [col for col in required_columns if col not in df.columns]
        
        if missing_columns:
            flash(f"❌ Chybějící sloupce v Excel souboru: {', '.join(missing_columns)}")
            return redirect(url_for("strediska.prehled_odbernych_mist", stredisko_id=stredisko_id))
        
        # Statistiky
        total_rows = len(df)
        added_count = 0
        skipped_count = 0
        error_count = 0
        
        # Zpracuj každý řádek
        for index, row in df.iterrows():
            try:
                # Přeskočit prázdné řádky
                if pd.isna(row['cislo_om']) or str(row['cislo_om']).strip() == '':
                    continue
                
                cislo_om = str(row['cislo_om']).strip()
                
                # Zkontroluj, zda odběrné místo již existuje
                existing_om = OdberneMisto.query.filter_by(
                    stredisko_id=stredisko_id, 
                    cislo_om=cislo_om
                ).first()
                
                if existing_om:
                    skipped_count += 1
                    continue
                
                # Vytvoř nové odběrné místo
                nove_om = OdberneMisto(
                    stredisko_id=stredisko_id,
                    cislo_om=cislo_om,
                    ean_om=safe_excel_string(row.get('ean_om', '')),
                    nazev_om=safe_excel_string(row.get('nazev_om', '')),
                    distribucni_sazba_om=safe_excel_string(row.get('distribucni_sazba_om', '')),
                    kategorie_jistice_om=safe_excel_string(row.get('kategorie_jistice_om', '')),
                    hodnota_jistice_om=safe_excel_string(row.get('hodnota_jistice_om', '')),
                    poznamka_om=safe_excel_string(row.get('poznamka_om', ''))
                )
                
                db.session.add(nove_om)
                added_count += 1
                
            except Exception as e:
                error_count += 1
                print(f"Chyba při zpracování řádku {index + 1}: {str(e)}")
                continue
        
        # Uložit změny do databáze
        try:
            db.session.commit()
            
            # Vytvoř zprávu o výsledku
            message_parts = []
            if added_count > 0:
                message_parts.append(f"✅ Přidáno {added_count} odběrných míst")
            if skipped_count > 0:
                message_parts.append(f"⚠️ Přeskočeno {skipped_count} duplicitních míst")
            if error_count > 0:
                message_parts.append(f"❌ {error_count} řádků s chybou")
            
            if message_parts:
                flash(" | ".join(message_parts))
            else:
                flash("⚠️ Nebyly zpracovány žádné řádky.")
                
        except Exception as e:
            db.session.rollback()
            flash(f"❌ Chyba při ukládání do databáze: {str(e)}")
    
    except Exception as e:
        flash(f"❌ Neočekávaná chyba: {str(e)}")
    
    return redirect(url_for("strediska.prehled_odbernych_mist", stredisko_id=stredisko_id))

@strediska_bp.route("/<int:stredisko_id>/upravit_odberne_misto", methods=["POST"])
@login_required
def upravit_odberne_misto(stredisko_id):
    has_access, error_response = check_stredisko_access(stredisko_id, 'write')
    if not has_access:
        return {"status": "error", "message": "Nemáte oprávnění"}, 403
    
    om_id = request.form.get('pk')
    field_name = request.form.get('name')
    new_value = request.form.get('value')
    
    om = OdberneMisto.query.filter_by(id=om_id, stredisko_id=stredisko_id).first()
    if not om:
        return {"status": "error", "message": "Odběrné místo nenalezeno"}, 404
    
    # Aktualizuj hodnotu
    setattr(om, field_name, new_value)
    db.session.commit()
    
    return {"status": "success", "message": "Hodnota byla aktualizována"}

@strediska_bp.route("/<int:stredisko_id>/smazat_odberne_misto", methods=["POST"])
@login_required
def smazat_odberne_misto(stredisko_id):
    has_access, error_response = check_stredisko_access(stredisko_id, 'write')
    if not has_access:
        return {"status": "error", "message": "Nemáte oprávnění"}, 403
    
    om_id = request.form.get('om_id')
    
    om = OdberneMisto.query.filter_by(id=om_id, stredisko_id=stredisko_id).first()
    if not om:
        return {"status": "error", "message": "Odběrné místo nenalezeno"}, 404
    
    cislo_om = om.cislo_om
    db.session.delete(om)
    db.session.commit()
    
    return {"status": "success", "message": f"Odběrné místo {cislo_om} bylo smazáno"}

@strediska_bp.route("/<int:stredisko_id>/smazat", methods=["POST"])
@login_required
def smazat_stredisko(stredisko_id):
    """Smaže středisko a všechna přináležející odběrná místa"""
    has_access, error_response = check_stredisko_access(stredisko_id, 'write')
    if not has_access:
        flash("❌ Nemáte oprávnění smazat toto středisko.")
        return redirect(url_for("strediska.spravovat_stredisko", stredisko_id=stredisko_id))

    stredisko = Stredisko.query.get_or_404(stredisko_id)
    
    try:
        # Zjisti počet odběrných míst před smazáním
        odberna_mista = OdberneMisto.query.filter_by(stredisko_id=stredisko_id).all()
        pocet_om = len(odberna_mista)
        
        # Smaž všechna odběrná místa tohoto střediska
        for om in odberna_mista:
            # Smaž také všechny odečty pro toto odběrné místo
            odecty = Odečet.query.filter_by(odberne_misto_id=om.id).all()
            for odecet in odecty:
                db.session.delete(odecet)
            
            # Smaž všechny výpočty pro toto odběrné místo
            vypocty = VypocetOM.query.filter_by(odberne_misto_id=om.id).all()
            for vypocet in vypocty:
                db.session.delete(vypocet)
            
            # Smaž odběrné místo
            db.session.delete(om)
        
        # Smaž všechna období fakturace pro toto středisko (nejdříve závislé záznamy)
        obdobi = ObdobiFakturace.query.filter_by(stredisko_id=stredisko_id).all()
        for okres in obdobi:
            # Smaž všechny záznamy odkazující na toto období fakturace
            
            # Faktury pro toto období
            faktury = Faktura.query.filter_by(obdobi_id=okres.id).all()
            for faktura in faktury:
                db.session.delete(faktura)
                
            # Zálohové faktury pro toto období
            zalohove_faktury = ZalohovaFaktura.query.filter_by(obdobi_id=okres.id).all()
            for zalohova_faktura in zalohove_faktury:
                db.session.delete(zalohova_faktura)
                
            # Import odečtů pro toto období
            importy_odectu = ImportOdečtu.query.filter_by(obdobi_id=okres.id).all()
            for import_odectu in importy_odectu:
                db.session.delete(import_odectu)
            
            # Ceny dodavatele pro toto období
            ceny_dodavatel = CenaDodavatel.query.filter_by(obdobi_id=okres.id).all()
            for cena in ceny_dodavatel:
                db.session.delete(cena)
                
            # Poznámka: CenaDistribuce nemá obdobi_id, ale stredisko_id - smaže se později
            
            # Teď už můžeme smazat období fakturace
            db.session.delete(okres)
        
        # Smaž ceny distribuce pro toto středisko
        ceny_distribuce = CenaDistribuce.query.filter_by(stredisko_id=stredisko_id).all()
        for cena in ceny_distribuce:
            db.session.delete(cena)
        
        # Smaž středisko
        nazev_strediska = stredisko.nazev_strediska
        db.session.delete(stredisko)
        
        # Commit všech změn
        db.session.commit()
        
        flash(f"✅ Středisko '{nazev_strediska}' a {pocet_om} odběrných míst bylo úspěšně smazáno.")
        return redirect(url_for("strediska.strediska"))
        
    except Exception as e:
        db.session.rollback()
        flash(f"❌ Chyba při mazání střediska: {str(e)}")
        return redirect(url_for("strediska.spravovat_stredisko", stredisko_id=stredisko_id))