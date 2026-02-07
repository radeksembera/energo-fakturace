from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from models import db, Stredisko, CenaDistribuce, CenaDodavatel, ObdobiFakturace
from routes.auth import login_required
from routes.strediska import check_stredisko_access
from utils.helpers import safe_excel_string
from session_helpers import handle_obdobi_selection, get_session_obdobi, set_session_obdobi
import pandas as pd
from datetime import datetime

ceny_bp = Blueprint("ceny", __name__)

@ceny_bp.route("/<int:stredisko_id>/ceny_distribuce")
@login_required
def ceny_distribuce(stredisko_id):
    has_access, error_response = check_stredisko_access(stredisko_id, 'read')
    if not has_access:
        flash("❌ Nemáte oprávnění k tomuto středisku.")
        return redirect("/strediska")

    stredisko = Stredisko.query.get_or_404(stredisko_id)
    
    # Pevný seznam dostupných roků
    dostupne_roky = [2024, 2025, 2026, 2027, 2028]
    
    # Získej vybraný rok z parametru, defaultně aktuální rok
    vybrany_rok = request.args.get('rok', default=datetime.now().year, type=int)
    
    # Filtruj ceny podle střediska a roku
    ceny = CenaDistribuce.query.filter_by(stredisko_id=stredisko_id, rok=vybrany_rok).all()
    
    return render_template("ceny_distribuce.html", 
                         stredisko=stredisko, 
                         ceny=ceny,
                         dostupne_roky=dostupne_roky,
                         vybrany_rok=vybrany_rok)

@ceny_bp.route("/<int:stredisko_id>/ceny_dodavatele")
@login_required
def ceny_dodavatele(stredisko_id):
    has_access, error_response = check_stredisko_access(stredisko_id, 'read')
    if not has_access:
        flash("❌ Nemáte oprávnění k tomuto středisku.")
        return redirect("/strediska")

    stredisko = Stredisko.query.get_or_404(stredisko_id)

    # Použij jednotný session helper pro výběr období
    vybrane_obdobi = handle_obdobi_selection(stredisko_id, request.args)

    # Pokud období neexistuje, vytvoř ho
    if not vybrane_obdobi:
        # Získej rok/měsíc z URL nebo session default
        url_rok = request.args.get("rok", type=int)
        url_mesic = request.args.get("mesic", type=int)

        if url_rok and url_mesic:
            vybrane_obdobi = ObdobiFakturace(
                stredisko_id=stredisko_id,
                rok=url_rok,
                mesic=url_mesic
            )
            db.session.add(vybrane_obdobi)
            db.session.commit()
            set_session_obdobi(stredisko_id, url_rok, url_mesic)

    zvoleny_rok = vybrane_obdobi.rok if vybrane_obdobi else 2025
    zvoleny_mesic = vybrane_obdobi.mesic if vybrane_obdobi else 1

    # Načti všechna období pro středisko (pro selectbox)
    vsechna_obdobi = ObdobiFakturace.query.filter_by(stredisko_id=stredisko_id)\
        .order_by(ObdobiFakturace.rok, ObdobiFakturace.mesic).all()

    # Načti dostupná období s cenami (pro rychlou navigaci)
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
                         stredisko=stredisko,
                         ceny=ceny,
                         zvoleny_rok=zvoleny_rok,
                         zvoleny_mesic=zvoleny_mesic,
                         vsechna_obdobi=vsechna_obdobi,
                         dostupna_obdobi=dostupna_obdobi,
                         vybrane_obdobi=vybrane_obdobi)

@ceny_bp.route("/<int:stredisko_id>/nahrat_ceny_distribuce", methods=["POST"])
@login_required
def nahrat_ceny_distribuce(stredisko_id):
    has_access, error_response = check_stredisko_access(stredisko_id, 'write')
    if not has_access:
        flash("❌ Nemáte oprávnění k úpravě tohoto střediska.")
        return redirect(url_for("ceny.ceny_distribuce", stredisko_id=stredisko_id))

    file = request.files.get("xlsx_file")

    # Získej rok z formuláře
    rok = request.form.get("rok", type=int)
    if not rok:
        rok = datetime.now().year

    if not file:
        flash("Nebyl vybrán žádný soubor.")
        return redirect(url_for("ceny.ceny_distribuce", stredisko_id=stredisko_id, rok=rok))

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

    return redirect(url_for("ceny.ceny_distribuce", stredisko_id=stredisko_id, rok=rok))

@ceny_bp.route("/<int:stredisko_id>/smazat_ceny_distribuce", methods=["POST"])
@login_required
def smazat_ceny_distribuce(stredisko_id):
    has_access, error_response = check_stredisko_access(stredisko_id, 'write')
    if not has_access:
        flash("❌ Nemáte oprávnění k úpravě tohoto střediska.")
        return redirect(url_for("ceny.ceny_distribuce", stredisko_id=stredisko_id))

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

    return redirect(url_for("ceny.ceny_distribuce", stredisko_id=stredisko_id, rok=rok))

@ceny_bp.route("/<int:stredisko_id>/nahrat_ceny_dodavatele", methods=["POST"])
@login_required
def nahrat_ceny_dodavatele(stredisko_id):
    has_access, error_response = check_stredisko_access(stredisko_id, 'write')
    if not has_access:
        flash("❌ Nemáte oprávnění k úpravě tohoto střediska.")
        return redirect(url_for("ceny.ceny_dodavatele", stredisko_id=stredisko_id))

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
        return redirect(url_for("ceny.ceny_dodavatele", stredisko_id=stredisko_id, rok=rok, mesic=mesic))
    
    if not file:
        flash("Nebyl vybrán žádný soubor.")
        return redirect(url_for("ceny.ceny_dodavatele", stredisko_id=stredisko_id, rok=rok, mesic=mesic))

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
                platba_za_elektrinu_vt=row["platba_za_elektrinu_vt"],
                platba_za_elektrinu_nt=row["platba_za_elektrinu_nt"],
                mesicni_plat=row["mesicni_plat"]
            )
            db.session.add(zaznam)

        db.session.commit()
        flash(f"✅ Import cen dodavatele pro {rok}/{mesic:02d} proběhl v pořádku.")
    except Exception as e:
        flash(f"❌ Chyba při importu: {e}")

    return redirect(url_for("ceny.ceny_dodavatele", stredisko_id=stredisko_id, rok=rok, mesic=mesic))

@ceny_bp.route("/<int:stredisko_id>/smazat_ceny_dodavatele", methods=["POST"])
@login_required
def smazat_ceny_dodavatele(stredisko_id):
    has_access, error_response = check_stredisko_access(stredisko_id, 'write')
    if not has_access:
        flash("❌ Nemáte oprávnění k úpravě tohoto střediska.")
        return redirect(url_for("ceny.ceny_dodavatele", stredisko_id=stredisko_id))

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

    return redirect(url_for("ceny.ceny_dodavatele", stredisko_id=stredisko_id, rok=rok, mesic=mesic))

@ceny_bp.route("/<int:stredisko_id>/kopirovat_ceny_dodavatele", methods=["POST"])
@login_required
def kopirovat_ceny_dodavatele(stredisko_id):
    has_access, error_response = check_stredisko_access(stredisko_id, 'write')
    if not has_access:
        flash("❌ Nemáte oprávnění k úpravě tohoto střediska.")
        return redirect(url_for("ceny.ceny_dodavatele", stredisko_id=stredisko_id))

    try:
        # Získej cílový rok a měsíc z formuláře
        cilovy_rok = request.form.get("rok", type=int)
        cilovy_mesic = request.form.get("mesic", type=int)
        
        if not cilovy_rok or not cilovy_mesic:
            flash("❌ Chybí parametry roku nebo měsíce.")
            return redirect(url_for("ceny.ceny_dodavatele", stredisko_id=stredisko_id))

        # Najdi cílové období
        cilove_obdobi = ObdobiFakturace.query.filter_by(
            stredisko_id=stredisko_id,
            rok=cilovy_rok,
            mesic=cilovy_mesic
        ).first()
        
        if not cilove_obdobi:
            flash(f"❌ Cílové období {cilovy_rok}/{cilovy_mesic:02d} neexistuje.")
            return redirect(url_for("ceny.ceny_dodavatele", stredisko_id=stredisko_id))

        # Zkontroluj, jestli už cílové období nemá ceny
        existujici_ceny = CenaDodavatel.query.filter_by(obdobi_id=cilove_obdobi.id).count()
        if existujici_ceny > 0:
            flash(f"❌ Období {cilovy_rok}/{cilovy_mesic:02d} už obsahuje {existujici_ceny} cen. Nejprve je smažte.")
            return redirect(url_for("ceny.ceny_dodavatele", stredisko_id=stredisko_id, rok=cilovy_rok, mesic=cilovy_mesic))

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
            return redirect(url_for("ceny.ceny_dodavatele", stredisko_id=stredisko_id, rok=cilovy_rok, mesic=cilovy_mesic))

        # Načti ceny z předchozího období
        predchozi_ceny = CenaDodavatel.query.filter_by(obdobi_id=predchozi_obdobi.id).all()
        
        if not predchozi_ceny:
            flash(f"❌ Předchozí období {predchozi_rok}/{predchozi_mesic:02d} neobsahuje žádné ceny.")
            return redirect(url_for("ceny.ceny_dodavatele", stredisko_id=stredisko_id, rok=cilovy_rok, mesic=cilovy_mesic))

        # Kopíruj ceny do nového období
        zkopirowano = 0
        for puvodni_cena in predchozi_ceny:
            nova_cena = CenaDodavatel(
                stredisko_id=stredisko_id,
                obdobi_id=cilove_obdobi.id,  # Nové období
                distribuce=puvodni_cena.distribuce,
                sazba=puvodni_cena.sazba,
                platba_za_elektrinu_vt=puvodni_cena.platba_za_elektrinu_vt,
                platba_za_elektrinu_nt=puvodni_cena.platba_za_elektrinu_nt,
                mesicni_plat=puvodni_cena.mesicni_plat
            )
            db.session.add(nova_cena)
            zkopirowano += 1

        db.session.commit()
        
        flash(f"✅ Úspěšně zkopírováno {zkopirowano} cen z období {predchozi_rok}/{predchozi_mesic:02d} do {cilovy_rok}/{cilovy_mesic:02d}.")
        
        # Přesměruj na cílové období
        return redirect(url_for("ceny.ceny_dodavatele", stredisko_id=stredisko_id, rok=cilovy_rok, mesic=cilovy_mesic))

    except Exception as e:
        db.session.rollback()
        flash(f"❌ Chyba při kopírování cen: {str(e)}")
        return redirect(url_for("ceny.ceny_dodavatele", stredisko_id=stredisko_id))

@ceny_bp.route("/<int:stredisko_id>/hromadne_upravit_ceny_dodavatele", methods=["POST"])
@login_required
def hromadne_upravit_ceny_dodavatele(stredisko_id):
    """Hromadná úprava všech cen dodavatele pro dané období"""
    has_access, error_response = check_stredisko_access(stredisko_id, 'write')
    if not has_access:
        flash("❌ Nemáte oprávnění k úpravě tohoto střediska.")
        return redirect(url_for("ceny.ceny_dodavatele", stredisko_id=stredisko_id))

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
            return redirect(url_for("ceny.ceny_dodavatele", stredisko_id=stredisko_id, rok=rok, mesic=mesic))
        
        if any(x < 0 for x in [platba_za_elektrinu_vt, platba_za_elektrinu_nt, mesicni_plat]):
            flash("❌ Ceny nemohou být záporné.")
            return redirect(url_for("ceny.ceny_dodavatele", stredisko_id=stredisko_id, rok=rok, mesic=mesic))

        # Najdi období
        obdobi = ObdobiFakturace.query.filter_by(
            stredisko_id=stredisko_id,
            rok=rok,
            mesic=mesic
        ).first()
        
        if not obdobi:
            flash(f"❌ Období {rok}/{mesic:02d} neexistuje.")
            return redirect(url_for("ceny.ceny_dodavatele", stredisko_id=stredisko_id))

        # Spočítej kolik záznamů bude ovlivněno
        pocet_zaznamu = CenaDodavatel.query.filter_by(obdobi_id=obdobi.id).count()
        
        if pocet_zaznamu == 0:
            flash(f"❌ Pro období {rok}/{mesic:02d} nebyly nalezeny žádné ceny k úpravě.")
            return redirect(url_for("ceny.ceny_dodavatele", stredisko_id=stredisko_id, rok=rok, mesic=mesic))

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

    except ValueError as e:
        flash(f"❌ Neplatné hodnoty: {str(e)}")
        return redirect(url_for("ceny.ceny_dodavatele", stredisko_id=stredisko_id, rok=rok, mesic=mesic))
    except Exception as e:
        db.session.rollback()
        flash(f"❌ Chyba při úpravě cen: {str(e)}")
        return redirect(url_for("ceny.ceny_dodavatele", stredisko_id=stredisko_id, rok=rok, mesic=mesic))

    return redirect(url_for("ceny.ceny_dodavatele", stredisko_id=stredisko_id, rok=rok, mesic=mesic))