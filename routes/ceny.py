from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from models import db, Stredisko, CenaDistribuce, CenaDodavatel
from routes.auth import login_required
from routes.strediska import check_stredisko_access
from utils.helpers import safe_excel_string
import pandas as pd
from datetime import datetime

ceny_bp = Blueprint("ceny", __name__)

@ceny_bp.route("/strediska/<int:stredisko_id>/ceny_distribuce")
@login_required
def ceny_distribuce(stredisko_id):
    has_access, error_response = check_stredisko_access(stredisko_id, 'read')
    if not has_access:
        flash("❌ Nemáte oprávnění k tomuto středisku.")
        return redirect("/strediska")

    stredisko = Stredisko.query.get_or_404(stredisko_id)
    ceny = CenaDistribuce.query.filter_by(stredisko_id=stredisko_id).order_by(
        CenaDistribuce.rok.desc(), 
        CenaDistribuce.mesic.desc()
    ).all()
    
    return render_template("ceny_distribuce.html", stredisko=stredisko, ceny=ceny)

@ceny_bp.route("/strediska/<int:stredisko_id>/ceny_dodavatele")
@login_required 
def ceny_dodavatele(stredisko_id):
    has_access, error_response = check_stredisko_access(stredisko_id, 'read')
    if not has_access:
        flash("❌ Nemáte oprávnění k tomuto středisku.")
        return redirect("/strediska")

    stredisko = Stredisko.query.get_or_404(stredisko_id)
    
    # Načti ceny dodavatele seřazené podle období
    ceny = CenaDodavatel.query.filter_by(stredisko_id=stredisko_id).order_by(
        CenaDodavatel.rok.desc(), 
        CenaDodavatel.mesic.desc()
    ).all()
    
    # Seskupit podle období
    ceny_podle_obdobi = {}
    for cena in ceny:
        klic = (cena.rok, cena.mesic)
        if klic not in ceny_podle_obdobi:
            ceny_podle_obdobi[klic] = []
        ceny_podle_obdobi[klic].append(cena)
    
    return render_template("ceny_dodavatele.html", 
                         stredisko=stredisko, 
                         ceny_podle_obdobi=ceny_podle_obdobi)