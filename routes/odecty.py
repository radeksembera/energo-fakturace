from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from models import db, Stredisko, ImportOdečtu, Odečet, ZalohovaFaktura, ObdobiFakturace
# Alias pro zpětnou kompatibilitu s kódem bez diakritiky
ImportOdectu = ImportOdečtu
Odecet = Odečet
from session_helpers import handle_obdobi_selection, get_session_obdobi
import pandas as pd

odecty_bp = Blueprint("odecty", __name__, template_folder="templates/fakturace")

# osetreni 00 v importu odectu 
def safe_oznaceni_string(value):
    """Bezpečně převede hodnotu na string s zachováním vedoucích nul pro označení OM"""
    if pd.isna(value) or value == "":
        return ""
    
    # Pokud je to číslo, převeď na string s 7 znaky a vedoucími nulami
    if isinstance(value, (int, float)):
        return f"{int(value):07d}"
    
    # Pokud je to už string, zachovej jak je (pro případy jako "0014002")
    return str(value).strip()

@odecty_bp.route("/<int:stredisko_id>/odecty")
def odecty(stredisko_id):
    if not session.get("user_id"):
        return redirect("/login")

    # Načti středisko a ověř vlastnictví
    stredisko = Stredisko.query.get_or_404(stredisko_id)
    if stredisko.user_id != session["user_id"] and not session.get("is_admin"):
        return "Nepovolený přístup", 403

    # ✅ NOVÉ - jednotná správa období
    vsechna_obdobi = ObdobiFakturace.query.filter_by(stredisko_id=stredisko_id)\
        .order_by(ObdobiFakturace.rok, ObdobiFakturace.mesic).all()

    # Zpracuj výběr období ze session
    vybrane_obdobi = handle_obdobi_selection(stredisko_id, request.args)

    # Načti importy podle vybraného období
    importy = []
    if vybrane_obdobi:
        importy = ImportOdectu.query.filter_by(
            stredisko_id=stredisko_id,
            obdobi_id=vybrane_obdobi.id
        ).all()

    return render_template(
        "fakturace/import_odectu.html",
        stredisko=stredisko,
        vsechna_obdobi=vsechna_obdobi,
        vybrane_obdobi=vybrane_obdobi,
        importy=importy
    )


@odecty_bp.route("/<int:stredisko_id>/import_odectu/nahrat", methods=["POST"])
def nahrat_import_odectu(stredisko_id):
    if not session.get("user_id"):
        return redirect("/login")

    obdobi_id = request.args.get("obdobi_id", type=int)
    if not obdobi_id:
        flash("Chybí parametr období.")
        return redirect(url_for("odecty.odecty", stredisko_id=stredisko_id))

    file = request.files.get("xlsx_file")
    if not file or file.filename == "":
        flash("Nebyl vybrán žádný soubor.")
        return redirect(url_for("odecty.odecty", stredisko_id=stredisko_id, obdobi_id=obdobi_id))

    try:
        print("Začíná import...")
        # Načteme Excel soubor (.xls nebo .xlsx)
        df = pd.read_excel(file)
        print("🧠 Načtené sloupce:", df.columns.tolist())

        vybrane_obdobi = ObdobiFakturace.query.get(obdobi_id)
        if not vybrane_obdobi:
            flash("Zvolené období neexistuje.")
            return redirect(url_for("odecty.odecty", stredisko_id=stredisko_id))

        # Nejprve smažeme staré importy pro toto období
        ImportOdectu.query.filter_by(
            stredisko_id=stredisko_id,
            obdobi_id=obdobi_id
        ).delete()

        uspesne_importy = 0
        chyby = []

        for index, row in df.iterrows():
            try:
                # Bezpečné načtení volitelných sloupců
                try:
                    # Sloupec O (index 14) - slevovy_bonus
                    if len(row) > 14 and pd.notnull(row.iloc[14]) and row.iloc[14] != 0:
                        slevovy_bonus = float(row.iloc[14])
                    else:
                        slevovy_bonus = None
                    
                    # Sloupec P (index 15) - dofakturace  
                    if len(row) > 15 and pd.notnull(row.iloc[15]) and row.iloc[15] != 0:
                        dofakturace = float(row.iloc[15])
                    else:
                        dofakturace = None
                    
                    # Sloupec R (index 17) - priznak
                    if len(row) > 17 and pd.notnull(row.iloc[17]) and str(row.iloc[17]).strip() != "":
                        priznak = str(row.iloc[17]).strip()
                    else:
                        priznak = None

                    # Debug výpis pro kontrolu
                    print(f"🔍 Řádek {index + 2}: slevovy_bonus={slevovy_bonus}, dofakturace={dofakturace}, priznak='{priznak}'")

                except (IndexError, ValueError) as e:
                    # Fallback hodnoty pokud se něco pokazí
                    slevovy_bonus = None
                    dofakturace = None
                    priznak = None
                    print(f"⚠️ Chyba při čtení volitelných sloupců řádku {index + 2}: {e}")

                # Zpracování dat podle nové struktury
                novy = ImportOdectu(
                    stredisko_id=int(stredisko_id),
                    import_rok=int(row["Rok"]),
                    import_mesic=int(row["Měsíc"]),
                    oznaceni_om=safe_oznaceni_string(row["oznaceni"]),  # ✅ OPRAVENO - zachová vedoucí nuly
                    nazev=str(row["Název"]),
                    textova_informace=str(row["Textová informace - Vše"]),
                    
                    # Zpracování dat - pokud jsou v Excel formátu, převedeme na datetime
                    zacatek_periody_mereni=pd.to_datetime(row["Začátek periody měření"], errors="coerce") if pd.notnull(row["Začátek periody měření"]) else None,
                    konec_periody_mereni=pd.to_datetime(row["Konec periody měření"], errors="coerce") if pd.notnull(row["Konec periody měření"]) else None,
                    datum_a_cas_odectu=pd.to_datetime(row["Skutečně odečteno"], errors="coerce") if pd.notnull(row["Skutečně odečteno"]) else None,
                    
                    zdroj_hodnoty=str(row.get("Zdroj hodnoty") or row.get("Zdroj hodnot", "")) if pd.notnull(row.get("Zdroj hodnoty") or row.get("Zdroj hodnot")) else "",
                    popis_dimenze=str(row["Popis dimenze"]) if pd.notnull(row["Popis dimenze"]) else "",
                    pocatecni_hodnota=float(row["PZ hodnota"]) if pd.notnull(row["PZ hodnota"]) else None,
                    hodnota_odectu=float(row["Hodnota odečtu"]) if pd.notnull(row["Hodnota odečtu"]) else None,
                    spotreba=float(row["Spotřeba s koeficientem dimenze"]) if pd.notnull(row["Spotřeba s koeficientem dimenze"]) else None,
                    merna_jednotka=str(row["Měrná jednotka"]) if pd.notnull(row["Měrná jednotka"]) else "",
                    
                    # Správně načtené volitelné hodnoty
                    slevovy_bonus=slevovy_bonus,
                    dofakturace=dofakturace,
                    priznak=priznak,
                    
                    zaloha_importu_kc=float(row.get("záloha č.", 0)) if pd.notnull(row.get("záloha č.")) else None,
                    
                    obdobi_id=int(obdobi_id)
                )

                db.session.add(novy)
                uspesne_importy += 1

            except Exception as e:
                chyba_msg = f"Řádek {index + 2}: {str(e)}"
                chyby.append(chyba_msg)
                print(f"❌ Chyba při zpracování řádku {index + 2}: {e}")
                print("Problematický řádek:", row.to_dict())

        db.session.commit()
        
        # Zprávy o výsledku
        if uspesne_importy > 0:
            flash(f"✅ Úspěšně importováno {uspesne_importy} záznamů.")
        
        if chyby:
            for chyba in chyby[:5]:  # Zobraz max 5 chyb
                flash(f"⚠️ {chyba}")
            if len(chyby) > 5:
                flash(f"⚠️ ... a dalších {len(chyby)-5} chyb")

    except Exception as e:
        print("❌ Výjimka při zpracování:", e)
        flash(f"❌ Chyba při importu: {e}")

    return redirect(url_for("odecty.odecty", stredisko_id=stredisko_id, obdobi_id=obdobi_id))


@odecty_bp.route("/<int:stredisko_id>/import_odectu/smazat", methods=["POST"])
def smazat_import_odectu(stredisko_id):
    if not session.get("user_id"):
        return redirect("/login")

    obdobi_id = request.args.get("obdobi_id", type=int)
    if not obdobi_id:
        flash("Chybí parametr období.")
        return redirect(url_for('odecty.odecty', stredisko_id=stredisko_id))

    try:
        # Smažeme podle stredisko_id a obdobi_id (ne podle import_rok/import_mesic)
        smazano = ImportOdectu.query.filter_by(
            stredisko_id=stredisko_id,
            obdobi_id=obdobi_id
        ).delete()
        
        db.session.commit()
        
        if smazano > 0:
            flash(f"✅ Import odečtů byl smazán ({smazano} záznamů).")
        else:
            flash("⚠️ Žádné záznamy k smazání nebyly nalezeny.")
            
    except Exception as e:
        flash(f"❌ Chyba při mazání: {e}")

    return redirect(url_for('odecty.odecty', stredisko_id=stredisko_id, obdobi_id=obdobi_id))


# Potvrzeni dat a predani do odectu

@odecty_bp.route("/<int:stredisko_id>/import_potvrdit", methods=["GET"])
def import_potvrdit(stredisko_id):
    if not session.get("user_id"):
        return redirect("/login")

    obdobi_id = request.args.get("obdobi_id", type=int)
    if not obdobi_id:
        flash("Chybí parametr období.")
        return redirect(url_for("odecty.odecty", stredisko_id=stredisko_id))

    importy = ImportOdectu.query.filter_by(stredisko_id=stredisko_id, obdobi_id=obdobi_id).all()
    if not importy:
        flash("Žádné importované odečty k potvrzení.")
        return redirect(url_for("odecty.odecty", stredisko_id=stredisko_id, obdobi_id=obdobi_id))

    try:
        # Nejprve smažeme staré odečty pro toto období
        Odecet.query.filter_by(
            stredisko_id=stredisko_id,
            obdobi_id=obdobi_id
        ).delete()

        # PŘIDÁNO: Výpočet celkové zálohy
        celkova_zaloha = sum(imp.zaloha_importu_kc or 0 for imp in importy)
        
        # PŘIDÁNO: Uložení zálohy do zalohova_faktura
        if celkova_zaloha > 0:
            # Najdi nebo vytvoř záznam zálohové faktury
            zaloha_faktura = ZalohovaFaktura.query.filter_by(
                stredisko_id=stredisko_id,
                obdobi_id=obdobi_id
            ).first()
            
            if not zaloha_faktura:
                zaloha_faktura = ZalohovaFaktura(
                    stredisko_id=stredisko_id,
                    obdobi_id=obdobi_id
                )
                db.session.add(zaloha_faktura)
            
            # Aktualizuj zálohu
            zaloha_faktura.zaloha = celkova_zaloha
            
            flash(f"💰 Záloha {celkova_zaloha:,.2f} Kč byla automaticky uložena do zálohové faktury.")

        # Zbytek původního kódu pro vytvoření odečtů...
        from collections import defaultdict
        odecty_dict = defaultdict(lambda: {
            'vt': None,
            'nt': None,
            'spolecne': None
        })

        # Seskupíme podle označení OM
        for imp in importy:
            key = imp.oznaceni_om
            
            if imp.popis_dimenze in ["Spotřeba VT", "VT"]:
                odecty_dict[key]['vt'] = imp
            elif imp.popis_dimenze in ["Spotřeba NT", "NT"]:
                odecty_dict[key]['nt'] = imp
            else:
                odecty_dict[key]['spolecne'] = imp

        # Vytvoříme kombinované odečty
        uspesne_odecty = 0
        for oznaceni_om, data in odecty_dict.items():
            vt_data = data['vt']
            nt_data = data['nt']
            spolecne_data = data['spolecne'] or vt_data or nt_data

            if not spolecne_data:
                continue

            novy_odecet = Odecet(
                stredisko_id=stredisko_id,
                oznaceni=oznaceni_om,
                zacatek_periody_mereni=spolecne_data.zacatek_periody_mereni,
                konec_periody_mereni=spolecne_data.konec_periody_mereni,
                
                # VT data
                pocatecni_hodnota_vt=vt_data.pocatecni_hodnota if vt_data else None,
                hodnota_odectu_vt=vt_data.hodnota_odectu if vt_data else None,
                spotreba_vt=vt_data.spotreba if vt_data else None,
                
                # NT data
                pocatecni_hodnota_nt=nt_data.pocatecni_hodnota if nt_data else None,
                hodnota_odectu_nt=nt_data.hodnota_odectu if nt_data else None,
                spotreba_nt=nt_data.spotreba if nt_data else None,
                
                # Ostatní data ze společného záznamu
                slevovy_bonus=spolecne_data.slevovy_bonus,
                dofakturace=spolecne_data.dofakturace,
                obdobi_id=obdobi_id
            )
            
            db.session.add(novy_odecet)
            uspesne_odecty += 1

        db.session.commit()
        flash(f"✅ Úspěšně vytvořeno {uspesne_odecty} kombinovaných odečtů ze {len(importy)} importovaných záznamů.")

    except Exception as e:
        db.session.rollback()
        flash(f"❌ Chyba při potvrzování: {e}")

    return redirect(url_for("odecty.odecty", stredisko_id=stredisko_id, obdobi_id=obdobi_id))


# Zobrazení odectu v kontrole

@odecty_bp.route("/<int:stredisko_id>/kontrola_odectu")
def kontrola_odectu(stredisko_id):
    if not session.get("user_id"):
        return redirect("/login")

    # Načti středisko a ověř vlastnictví
    stredisko = Stredisko.query.get_or_404(stredisko_id)
    if stredisko.user_id != session["user_id"] and not session.get("is_admin"):
        return "Nepovolený přístup", 403

    # ✅ NOVÉ - jednotná správa období
    vsechna_obdobi = ObdobiFakturace.query.filter_by(
        stredisko_id=stredisko_id
    ).order_by(ObdobiFakturace.rok, ObdobiFakturace.mesic).all()

    # Zpracuj výběr období ze session
    vybrane_obdobi = handle_obdobi_selection(stredisko_id, request.args)

    # Načti zpracované odečty podle vybraného období
    odecty = []
    if vybrane_obdobi:
        odecty = Odecet.query.filter_by(
            stredisko_id=stredisko_id,
            obdobi_id=vybrane_obdobi.id
        ).all()

    return render_template(
        "fakturace/kontrola_odectu.html",
        stredisko=stredisko,
        vsechna_obdobi=vsechna_obdobi,
        vybrane_obdobi=vybrane_obdobi,
        odecty=odecty
    )


@odecty_bp.route("/<int:stredisko_id>/upravit_odecet", methods=["POST"])
def upravit_odecet(stredisko_id):
    """API endpoint pro inline úpravu odečtu (dofakturace, slevovy_bonus)"""
    if not session.get("user_id"):
        return jsonify({"status": "error", "message": "Nejste přihlášeni"}), 401

    stredisko = Stredisko.query.get_or_404(stredisko_id)
    if stredisko.user_id != session["user_id"] and not session.get("is_admin"):
        return jsonify({"status": "error", "message": "Nepovolený přístup"}), 403

    try:
        odecet_id = request.form.get('pk')
        field_name = request.form.get('name')
        new_value = request.form.get('value')

        # Povolené sloupce pro úpravu
        allowed_fields = ['dofakturace', 'slevovy_bonus']
        if field_name not in allowed_fields:
            return jsonify({"status": "error", "message": f"Nepovolené pole: {field_name}"}), 400

        odecet = Odecet.query.get(odecet_id)
        if not odecet or odecet.stredisko_id != stredisko_id:
            return jsonify({"status": "error", "message": "Odečet nenalezen"}), 404

        # Převeď hodnotu na číslo
        if new_value == '' or new_value is None:
            numeric_value = None
        else:
            try:
                # Odstraň případné "Kč" a mezery
                clean_value = str(new_value).replace('Kč', '').replace(' ', '').replace(',', '.')
                numeric_value = float(clean_value)
            except ValueError:
                return jsonify({"status": "error", "message": "Neplatná číselná hodnota"}), 400

        setattr(odecet, field_name, numeric_value)
        db.session.commit()

        field_label = "Dofakturace" if field_name == "dofakturace" else "Bonus"
        return jsonify({
            "status": "success",
            "message": f"{field_label} byla úspěšně aktualizována"
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": f"Chyba při ukládání: {str(e)}"}), 500


@odecty_bp.route("/<int:stredisko_id>/smazat_odecet", methods=["POST"])
def smazat_odecet(stredisko_id):
    """API endpoint pro smazání odečtu"""
    if not session.get("user_id"):
        return jsonify({"status": "error", "message": "Nejste přihlášeni"}), 401

    stredisko = Stredisko.query.get_or_404(stredisko_id)
    if stredisko.user_id != session["user_id"] and not session.get("is_admin"):
        return jsonify({"status": "error", "message": "Nepovolený přístup"}), 403

    try:
        odecet_id = request.form.get('odecet_id')

        odecet = Odecet.query.get(odecet_id)
        if not odecet or odecet.stredisko_id != stredisko_id:
            return jsonify({"status": "error", "message": "Odečet nenalezen"}), 404

        oznaceni = odecet.oznaceni
        db.session.delete(odecet)
        db.session.commit()

        return jsonify({
            "status": "success",
            "message": f"Odečet pro OM {oznaceni} byl smazán"
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": f"Chyba při mazání: {str(e)}"}), 500