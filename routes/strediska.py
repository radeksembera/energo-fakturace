from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from models import db, User, Stredisko, OdberneMisto, VypocetOM, Odečet
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
        
        if OdberneMisto.query.filter_by(stredisko_id=stredisko_id, cislo_om=cislo_om).first():
            flash(f"❌ Odběrné místo s kódem {cislo_om} již existuje!")
        else:
            nove_om = OdberneMisto(
                stredisko_id=stredisko_id,
                cislo_om=cislo_om,
                nazev_om=nazev_om,
                distribucni_sazba_om=distribucni_sazba_om
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
        
        flash(f"✅ Středisko {nazev} bylo úspěšně vytvořeno.")
        return redirect(url_for("strediska.strediska"))

    return render_template("pridat_stredisko.html")