from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from models import db, Stredisko, InfoDodavatele, InfoVystavovatele, InfoOdberatele, ZalohovaFaktura, Faktura, ImportOdečtu, VypocetOM, OdberneMisto, CenaDistribuce, CenaDodavatel, Odečet, ObdobiFakturace, CislaFaktur, SumarizaceStrediska
from sqlalchemy import func
# Alias pro zpětnou kompatibilitu s kódem bez diakritiky
Odecet = Odečet
from session_helpers import handle_obdobi_selection, get_session_obdobi, get_dostupna_obdobi_pro_stredisko, set_session_obdobi
from file_helpers import check_faktury_exist



fakturace_bp = Blueprint("fakturace", __name__, template_folder="templates/fakturace")

# ----------------FAKTURACE--------------------------
@fakturace_bp.route("/<int:stredisko_id>/fakturace")
def fakturace(stredisko_id):
    if not session.get("user_id"):
        return redirect("/login")

    # Ověření vlastnictví střediska
    stredisko = Stredisko.query.get_or_404(stredisko_id)
    if stredisko.user_id != session["user_id"]:
        return "Nepovolený přístup", 403

    # Získej všechna dostupná období pro středisko
    dostupna_obdobi = get_dostupna_obdobi_pro_stredisko(stredisko_id)
    
    # Zpracuj výběr období a ulož do session
    vybrane_obdobi = handle_obdobi_selection(stredisko_id, request.args)

    if not vybrane_obdobi:
        flash("❌ Žádné období fakturace nebylo nalezeno.")
        return redirect(url_for("strediska.spravovat_stredisko", stredisko_id=stredisko_id))

    # Načti informace o subjektech pro kontrolu stavu
    dodavatel = InfoDodavatele.query.filter_by(stredisko_id=stredisko_id).first()
    vystavovatel = InfoVystavovatele.query.filter_by(stredisko_id=stredisko_id).first()
    odberatel = InfoOdberatele.query.filter_by(stredisko_id=stredisko_id).first()
    

    return render_template(
        "fakturace/prehled_fakturace.html",
        stredisko=stredisko,
        vybrane_obdobi=vybrane_obdobi,
        dostupna_obdobi=dostupna_obdobi,
        dodavatel=dodavatel,
        vystavovatel=vystavovatel,
        odberatel=odberatel
    )


@fakturace_bp.route("/<int:stredisko_id>/subjekty")
def subjekty_fakturace(stredisko_id):
    if not session.get("user_id"):
        return redirect("/login")

    stredisko = Stredisko.query.get_or_404(stredisko_id)
    if stredisko.user_id != session["user_id"]:
        return "Nepovolený přístup", 403

    dodavatel = InfoDodavatele.query.filter_by(stredisko_id=stredisko_id).first()
    vystavovatel = InfoVystavovatele.query.filter_by(stredisko_id=stredisko_id).first()
    odberatel = InfoOdberatele.query.filter_by(stredisko_id=stredisko_id).first()

    return render_template("fakturace/subjekty_fakturace.html",
                           stredisko=stredisko,
                           dodavatel=dodavatel,
                           vystavovatel=vystavovatel,
                           odberatel=odberatel)


@fakturace_bp.route("/<int:stredisko_id>/ulozit_dodavatele", methods=["POST"])
def ulozit_dodavatele(stredisko_id):
    if not session.get("user_id"):
        return redirect("/login")

    stredisko = Stredisko.query.get_or_404(stredisko_id)
    if stredisko.user_id != session["user_id"]:
        return "Nepovolený přístup", 403

    # Najdi nebo vytvoř záznam dodavatele
    dodavatel = InfoDodavatele.query.filter_by(stredisko_id=stredisko_id).first()
    if not dodavatel:
        dodavatel = InfoDodavatele(stredisko_id=stredisko_id)

    # Ulož data z formuláře
    dodavatel.nazev_sro = request.form.get("nazev_sro", "")
    dodavatel.adresa_radek_1 = request.form.get("adresa_radek_1", "")
    dodavatel.adresa_radek_2 = request.form.get("adresa_radek_2", "")
    dodavatel.ico_sro = request.form.get("ico_sro", "")
    dodavatel.dic_sro = request.form.get("dic_sro", "")
    dodavatel.zapis_u_soudu = request.form.get("zapis_u_soudu", "")
    dodavatel.banka = request.form.get("banka", "")
    dodavatel.cislo_uctu = request.form.get("cislo_uctu", "")
    dodavatel.swift = request.form.get("swift", "")
    dodavatel.iban = request.form.get("iban", "")

    db.session.add(dodavatel)
    db.session.commit()
    
    flash("✅ Informace o dodavateli byly úspěšně uloženy.")
    return redirect(url_for("fakturace.subjekty_fakturace", stredisko_id=stredisko_id))


@fakturace_bp.route("/<int:stredisko_id>/ulozit_vystavovatele", methods=["POST"])
def ulozit_vystavovatele(stredisko_id):
    if not session.get("user_id"):
        return redirect("/login")

    stredisko = Stredisko.query.get_or_404(stredisko_id)
    if stredisko.user_id != session["user_id"]:
        return "Nepovolený přístup", 403

    # Najdi nebo vytvoř záznam vystavovatele
    vystavovatel = InfoVystavovatele.query.filter_by(stredisko_id=stredisko_id).first()
    if not vystavovatel:
        vystavovatel = InfoVystavovatele(stredisko_id=stredisko_id)

    # Ulož data z formuláře
    vystavovatel.jmeno_vystavitele = request.form.get("jmeno_vystavitele", "")
    vystavovatel.telefon_vystavitele = request.form.get("telefon_vystavitele", "")
    vystavovatel.email_vystavitele = request.form.get("email_vystavitele", "")

    db.session.add(vystavovatel)
    db.session.commit()
    
    flash("✅ Informace o vystavovateli byly úspěšně uloženy.")
    return redirect(url_for("fakturace.subjekty_fakturace", stredisko_id=stredisko_id))


@fakturace_bp.route("/<int:stredisko_id>/ulozit_odberatele", methods=["POST"])
def ulozit_odberatele(stredisko_id):
    if not session.get("user_id"):
        return redirect("/login")

    stredisko = Stredisko.query.get_or_404(stredisko_id)
    if stredisko.user_id != session["user_id"]:
        return "Nepovolený přístup", 403

    # Najdi nebo vytvoř záznam odběratele
    odberatel = InfoOdberatele.query.filter_by(stredisko_id=stredisko_id).first()
    if not odberatel:
        odberatel = InfoOdberatele(stredisko_id=stredisko_id)

    # Ulož data z formuláře
    odberatel.nazev_sro = request.form.get("nazev_sro", "")
    odberatel.adresa_radek_1 = request.form.get("adresa_radek_1", "")
    odberatel.adresa_radek_2 = request.form.get("adresa_radek_2", "")
    odberatel.ico_sro = request.form.get("ico_sro", "")
    odberatel.dic_sro = request.form.get("dic_sro", "")

    db.session.add(odberatel)
    db.session.commit()
    
    flash("✅ Informace o odběrateli byly úspěšně uloženy.")
    return redirect(url_for("fakturace.subjekty_fakturace", stredisko_id=stredisko_id))


@fakturace_bp.route("/<int:stredisko_id>/koncove_ceny")
def koncove_ceny(stredisko_id):
    if not session.get("user_id"):
        return redirect("/login")

    stredisko = Stredisko.query.get_or_404(stredisko_id)
    if stredisko.user_id != session["user_id"]:
        return "Nepovolený přístup", 403

    # Načti odběrná místa
    odberna_mista = OdberneMisto.query.filter_by(stredisko_id=stredisko_id).all()

    print(f"🔍 DEBUG: Středisko ID: {stredisko_id}")
    
    # ✅ NOVÉ - jednotná správa období
    vsechna_obdobi = ObdobiFakturace.query.filter_by(
        stredisko_id=stredisko_id
    ).order_by(ObdobiFakturace.rok, ObdobiFakturace.mesic).all()
    
    # Zpracuj výběr období - speciální handling pro obdobi_id
    obdobi_id = request.args.get('obdobi_id', type=int)
    vybrane_obdobi = None
    
    if obdobi_id:
        # Najdi období podle ID
        obdobi = ObdobiFakturace.query.filter_by(
            id=obdobi_id,
            stredisko_id=stredisko_id
        ).first()
        
        if obdobi:
            set_session_obdobi(stredisko_id, obdobi.rok, obdobi.mesic)
            vybrane_obdobi = obdobi
    
    if not vybrane_obdobi:
        # Pokud není vybrané období, použij session nebo default
        vybrane_obdobi = get_session_obdobi(stredisko_id)

    # Načti výpočty pro vybrané období
    vypocty = []
    if vybrane_obdobi:
        vypocty = VypocetOM.query\
            .join(OdberneMisto)\
            .filter(OdberneMisto.stredisko_id == stredisko_id)\
            .filter(VypocetOM.obdobi_id == vybrane_obdobi.id)\
            .all()
    
    # Kontrola dostupnosti cen pro vybrané období
    pocet_cen_distribuce = 0
    pocet_cen_dodavatele = 0
    
    if vybrane_obdobi:
        # Ceny distribuce - podle roku
        pocet_cen_distribuce = CenaDistribuce.query.filter_by(
            stredisko_id=stredisko_id,
            rok=vybrane_obdobi.rok
        ).count()
        
        # Ceny dodavatele - podle období
        pocet_cen_dodavatele = CenaDodavatel.query.filter_by(
            # Období se řídí pouze přes ObdobiFakturace
        ).count()
    
    ma_ceny_distribuce = pocet_cen_distribuce > 0
    ma_ceny_dodavatele = pocet_cen_dodavatele > 0

    return render_template("fakturace/koncove_ceny.html", 
                           stredisko=stredisko,
                           vypocty=vypocty,
                           odberna_mista=odberna_mista,
                           pocet_cen_distribuce=pocet_cen_distribuce,
                           pocet_cen_dodavatele=pocet_cen_dodavatele,
                           ma_ceny_distribuce=ma_ceny_distribuce,
                           ma_ceny_dodavatele=ma_ceny_dodavatele,
                           vsechna_obdobi=vsechna_obdobi,
                           vybrane_obdobi=vybrane_obdobi)

@fakturace_bp.route("/<int:stredisko_id>/prepocitat_koncove_ceny")
def prepocitat_koncove_ceny(stredisko_id):
    """Přepočítá koncové ceny pro všechna odběrná místa s komplexními výpočty"""
    if not session.get("user_id"):
        return redirect("/login")

    stredisko = Stredisko.query.get_or_404(stredisko_id)
    if stredisko.user_id != session["user_id"]:
        return "Nepovolený přístup", 403

    try:
        from datetime import datetime
        import calendar
        vybrane_obdobi = get_session_obdobi(stredisko_id)
        aktualni_rok = vybrane_obdobi.rok         # 2025
        aktualni_mesic = vybrane_obdobi.mesic     # 6 (červen!)
        
        # Načti všechna odběrná místa
        odberna_mista = OdberneMisto.query.filter_by(stredisko_id=stredisko_id).all()
        
        if not odberna_mista:
            flash("❌ Nejsou definována žádná odběrná místa.")
            return redirect(url_for("fakturace.koncove_ceny", stredisko_id=stredisko_id))

        # Najdi období pro výpočet (aktuální měsíc/rok)
        obdobi_vypoctu = ObdobiFakturace.query.filter_by(
            stredisko_id=stredisko_id,
            rok=aktualni_rok,
            mesic=aktualni_mesic
        ).first()
        
        if not obdobi_vypoctu:
            flash(f"❌ Období {aktualni_rok}/{aktualni_mesic:02d} neexistuje. Vytvořte jej nejprve.")
            return redirect(url_for("fakturace.koncove_ceny", stredisko_id=stredisko_id))

        # Načti fakturu pro DPH
        faktura = Faktura.query.filter_by(stredisko_id=stredisko_id).first()
        sazba_dph = float(faktura.sazba_dph / 100) if faktura and faktura.sazba_dph else 0.21

        # Smaž staré výpočty pro toto období a středisko
        # Nejprve najdi ID výpočtů k smazání
        vypocty_ids = db.session.query(VypocetOM.id)\
            .join(OdberneMisto)\
            .filter(OdberneMisto.stredisko_id == stredisko_id)\
            .filter(VypocetOM.obdobi_id == obdobi_vypoctu.id)\
            .scalar_subquery()
        
        # Poté je smaž pomocí IN dotazu
        VypocetOM.query.filter(VypocetOM.id.in_(
            db.session.query(VypocetOM.id)\
                .join(OdberneMisto)\
                .filter(OdberneMisto.stredisko_id == stredisko_id)\
                .filter(VypocetOM.obdobi_id == obdobi_vypoctu.id)
        )).delete(synchronize_session=False)

        uspesne_vypocty = 0
        chyby = []

        for om in odberna_mista:
            try:
                print(f"🔍 Zpracovávám OM: {om.cislo_om}")
                print(f"   - distribucni_sazba_om: '{om.distribucni_sazba_om}'")
                print(f"   - hodnota_jistice_om: '{om.hodnota_jistice_om}'")
                print(f"   - stredisko.distribuce: '{stredisko.distribuce}'")
                
                # Najdi odečty pro toto konkrétní OM
                odecet = Odecet.query.filter_by(
                    stredisko_id=stredisko_id,
                    obdobi_id=obdobi_vypoctu.id,
                    oznaceni=om.cislo_om.zfill(7) if om.cislo_om else om.cislo_om
                ).first()

                if not odecet:
                    chyby.append(f"OM {om.cislo_om}: Nenalezen odečet")
                    continue

                # ✅ VYPOČÍTEJ POMĚR OBDOBÍ FAKTURACE
                delka_obdobi_fakturace = 1.0  # výchozí = celý měsíc
                if odecet.zacatek_periody_mereni and odecet.konec_periody_mereni:
                    # Vypočítej počet dní v období
                    pocet_dni_obdobi = (odecet.konec_periody_mereni - odecet.zacatek_periody_mereni).days + 1

                    # Zjisti měsíc z konce období měření (protože chceme počet dní toho měsíce)
                    mesic_mereni = odecet.konec_periody_mereni.month
                    rok_mereni = odecet.konec_periody_mereni.year

                    # Zjisti počet dní v daném měsíci
                    pocet_dni_mesice = calendar.monthrange(rok_mereni, mesic_mereni)[1]

                    # Vypočítej poměr
                    if pocet_dni_obdobi == pocet_dni_mesice:
                        # Období je celý měsíc
                        delka_obdobi_fakturace = 1.0
                    else:
                        # Poměr = počet dní období / celkový počet dní měsíce
                        delka_obdobi_fakturace = round(pocet_dni_obdobi / pocet_dni_mesice, 3)

                    print(f"📅 OM {om.cislo_om}: {odecet.zacatek_periody_mereni.strftime('%d.%m')} - {odecet.konec_periody_mereni.strftime('%d.%m')} = {pocet_dni_obdobi}/{pocet_dni_mesice} dní, poměr = {delka_obdobi_fakturace}")
                else:
                    print(f"⚠️ OM {om.cislo_om}: Chybí data o periodě měření, používám výchozí poměr 1.0")
                
                # Najdi ceny distribuce
                print(f"🔍 Hledám ceny distribuce pro:")
                print(f"   - stredisko_id: {stredisko_id}")
                print(f"   - rok: {aktualni_rok}")
                print(f"   - distribuce: '{stredisko.distribuce}'")
                print(f"   - sazba: '{om.distribucni_sazba_om}'")
                print(f"   - jistic: '{om.kategorie_jistice_om}'")
                
                cena_distribuce = CenaDistribuce.query.filter_by(
                    stredisko_id=stredisko_id,
                    rok=aktualni_rok,
                    distribuce=stredisko.distribuce,
                    sazba=om.distribucni_sazba_om,
                    jistic=om.kategorie_jistice_om  
                ).first()
                
                print(f"   - Nalezeno: {cena_distribuce is not None}")
                
                if not cena_distribuce:
                    print("❌ Nenalezena cena distribuce - kontroluji dostupné záznamy:")
                    dostupne = CenaDistribuce.query.filter_by(stredisko_id=stredisko_id, rok=aktualni_rok).all()
                    for d in dostupne[:3]:  # Zobraz jen první 3
                        print(f"   - distribuce:'{d.distribuce}', sazba:'{d.sazba}', jistic:'{d.jistic}'")
                    chyby.append(f"OM {om.cislo_om}: Nenalezena cena distribuce")
                    continue

                # Najdi ceny dodavatele - podle období
                cena_dodavatel = CenaDodavatel.query.filter_by(
                    obdobi_id=obdobi_vypoctu.id,
                    distribuce=stredisko.distribuce,
                    sazba=om.distribucni_sazba_om
                ).first()

                if not cena_dodavatel:
                    chyby.append(f"OM {om.cislo_om}: Nenalezena cena dodavatele")
                    continue

                # Získej spotřeby (v kWh)
                spotreba_vt = float(odecet.spotreba_vt or 0)
                spotreba_nt = float(odecet.spotreba_nt or 0)
                celkova_spotreba = spotreba_vt + spotreba_nt
                hodnota_jistice = float(om.hodnota_jistice_om or 0)

                # === VÝPOČTY PODLE VZORCŮ ===

                # 1. platba_za_jistic (vynásobeno poměrem období)
                if om.kategorie_jistice_om in ["nad 1x25A za každou 1A", "nad 3x160A za každou 1A", "nad 3x63A za každou 1A"]:
                    platba_za_jistic = float(cena_distribuce.platba_za_jistic or 0) * hodnota_jistice * delka_obdobi_fakturace
                else:
                    platba_za_jistic = float(cena_distribuce.platba_za_jistic or 0) * delka_obdobi_fakturace

                # 2. platba_za_distribuci_vt = spotreba_vt/1000 * cena_vt
                platba_za_distribuci_vt = (spotreba_vt / 1000) * float(cena_distribuce.platba_za_distribuci_vt or 0)

                # 3. platba_za_distribuci_nt = spotreba_nt/1000 * cena_nt  
                platba_za_distribuci_nt = (spotreba_nt / 1000) * float(cena_distribuce.platba_za_distribuci_nt or 0)

                # 4. systemove_sluzby = (spotreba_vt + spotreba_nt)/1000 * cena
                systemove_sluzby = (celkova_spotreba / 1000) * float(cena_distribuce.systemove_sluzby or 0)

                # 5. poze_dle_jistice = cena * hodnota_jistice * poměr období
                # U třífázových jističů (obsahují "3x") násobíme ještě 3 (3 fáze)
                poze_dle_jistice = float(cena_distribuce.poze_dle_jistice or 0) * hodnota_jistice
                if om.kategorie_jistice_om and "3x" in om.kategorie_jistice_om:
                    poze_dle_jistice = poze_dle_jistice * 3
                # Vynásobit poměrem období
                poze_dle_jistice = poze_dle_jistice * delka_obdobi_fakturace

                # 6. poze_dle_spotreby = celkova_spotreba/1000 * cena
                poze_dle_spotreby = (celkova_spotreba / 1000) * float(cena_distribuce.poze_dle_spotreby or 0)

                # 7. nesitova_infrastruktura = cena * poměr období
                nesitova_infrastruktura = float(cena_distribuce.nesitova_infrastruktura or 0) * delka_obdobi_fakturace

                # 8. dan_z_elektriny = cena * celkova_spotreba/1000
                dan_z_elektriny = float(cena_distribuce.dan_z_elektriny or 0) * (celkova_spotreba / 1000)

                # 9. platba_za_elektrinu_vt = spotreba_vt/1000 * cena
                platba_za_elektrinu_vt = (spotreba_vt / 1000) * float(cena_dodavatel.platba_za_elektrinu_vt or 0)

                # 10. platba_za_elektrinu_nt = spotreba_nt/1000 * cena
                platba_za_elektrinu_nt = (spotreba_nt / 1000) * float(cena_dodavatel.platba_za_elektrinu_nt or 0)

                # 11. mesicni_plat = cena * poměr období
                mesicni_plat = float(cena_dodavatel.mesicni_plat or 0) * delka_obdobi_fakturace

                # 12. zaklad_bez_dph = suma všech složek + MIN(poze_dle_jistice, poze_dle_spotreby)
                poze_minimum = min(poze_dle_jistice, poze_dle_spotreby)
                zaklad_bez_dph = (
                    platba_za_jistic + 
                    platba_za_distribuci_vt + 
                    platba_za_distribuci_nt + 
                    systemove_sluzby + 
                    poze_minimum + 
                    nesitova_infrastruktura + 
                    dan_z_elektriny + 
                    platba_za_elektrinu_vt + 
                    platba_za_elektrinu_nt + 
                    mesicni_plat
                )

                # 13. castka_dph = zaklad_bez_dph * sazba_dph
                castka_dph = zaklad_bez_dph * sazba_dph

                # 14. celkem_vc_dph = zaklad_bez_dph + castka_dph
                celkem_vc_dph = zaklad_bez_dph + castka_dph

                # === VÝPOČTY JEN DISTRIBUCE ===
                # Základ bez DPH jen distribučních poplatků
                zaklad_bez_dph_bez_di = (
                    # Jen distribuce: platba_za_jistic, platba_za_distribuci_vt, platba_za_distribuci_nt, systemove_sluzby, poze_minimum, nesitova_infrastruktura
                    platba_za_jistic +
                    platba_za_distribuci_vt +
                    platba_za_distribuci_nt +
                    systemove_sluzby +
                    poze_minimum +
                    nesitova_infrastruktura
                    # Nezahrnuje: dan_z_elektriny, platba_za_elektrinu_vt, platba_za_elektrinu_nt, mesicni_plat
                )

                # DPH jen distribuce
                castka_dph_bez_di = zaklad_bez_dph_bez_di * sazba_dph

                # Celkem s DPH jen distribuce
                celkem_vc_dph_bez_di = zaklad_bez_dph_bez_di + castka_dph_bez_di

                # Vytvoř výpočet
                vypocet = VypocetOM(
                    odberne_misto_id=om.id,
                    obdobi_id=obdobi_vypoctu.id,
                    delka_obdobi_fakturace=delka_obdobi_fakturace,
                    spotreba_om=round(celkova_spotreba, 2),  # Celková spotřeba OM (VT + NT) v kWh

                    # Distribuce
                    platba_za_jistic=round(platba_za_jistic, 2),
                    platba_za_distribuci_vt=round(platba_za_distribuci_vt, 2),
                    platba_za_distribuci_nt=round(platba_za_distribuci_nt, 2),
                    systemove_sluzby=round(systemove_sluzby, 2),
                    poze_dle_jistice=round(poze_dle_jistice, 2),
                    poze_dle_spotreby=round(poze_dle_spotreby, 2),
                    nesitova_infrastruktura=round(nesitova_infrastruktura, 2),
                    dan_z_elektriny=round(dan_z_elektriny, 2),
                    
                    # Dodavatel
                    platba_za_elektrinu_vt=round(platba_za_elektrinu_vt, 2),
                    platba_za_elektrinu_nt=round(platba_za_elektrinu_nt, 2),
                    mesicni_plat=round(mesicni_plat, 2),
                    
                    # Celkové výpočty
                    zaklad_bez_dph=round(zaklad_bez_dph, 2),
                    castka_dph=round(castka_dph, 2),
                    celkem_vc_dph=round(celkem_vc_dph, 2),

                    # Výpočty jen distribuce
                    zaklad_bez_dph_bez_di=round(zaklad_bez_dph_bez_di, 2),
                    castka_dph_bez_di=round(castka_dph_bez_di, 2),
                    celkem_vc_dph_bez_di=round(celkem_vc_dph_bez_di, 2)
                )

                db.session.add(vypocet)
                uspesne_vypocty += 1

            except Exception as e:
                chyby.append(f"OM {om.cislo_om}: Chyba při výpočtu - {str(e)}")

        # ✅ SUMARIZACE STŘEDISKA - Vypočítej a ulož celkové sumy pro středisko a období
        if uspesne_vypocty > 0:
            # Sečti všechny spotřeby a ceny pro toto středisko a období
            sumy = db.session.query(
                func.sum(VypocetOM.spotreba_om).label('celkova_spotreba'),
                func.sum(VypocetOM.celkem_vc_dph).label('celkova_cena_s_dph')
            ).join(OdberneMisto)\
             .filter(OdberneMisto.stredisko_id == stredisko_id)\
             .filter(VypocetOM.obdobi_id == obdobi_vypoctu.id)\
             .first()

            celkova_spotreba = float(sumy.celkova_spotreba) if sumy.celkova_spotreba else 0.0
            celkova_cena_s_dph = float(sumy.celkova_cena_s_dph) if sumy.celkova_cena_s_dph else 0.0

            # Najdi nebo vytvoř záznam sumarizace
            sumarizace = SumarizaceStrediska.query.filter_by(
                stredisko_id=stredisko_id,
                obdobi_id=obdobi_vypoctu.id
            ).first()

            if not sumarizace:
                sumarizace = SumarizaceStrediska(
                    stredisko_id=stredisko_id,
                    obdobi_id=obdobi_vypoctu.id,
                    rok=aktualni_rok,
                    mesic=aktualni_mesic
                )

            sumarizace.celkova_spotreba = celkova_spotreba
            sumarizace.celkova_cena_s_dph = celkova_cena_s_dph

            db.session.add(sumarizace)

        db.session.commit()

        if uspesne_vypocty > 0:
            flash(f"✅ Úspěšně vypočítáno {uspesne_vypocty} odběrných míst pro období {aktualni_rok}/{aktualni_mesic:02d}.")
        
        if chyby:
            for chyba in chyby[:5]:
                flash(f"⚠️ {chyba}")
            if len(chyby) > 5:
                flash(f"⚠️ ... a dalších {len(chyby)-5} chyb")

    except Exception as e:
        flash(f"❌ Chyba při přepočtu: {str(e)}")

    return redirect(url_for("fakturace.koncove_ceny", stredisko_id=stredisko_id))

# V fakturace_routes.py - oprava funkce smazat_vypocty

@fakturace_bp.route("/<int:stredisko_id>/smazat_vypocty")
def smazat_vypocty(stredisko_id):
    """Smaže všechny výpočty pro vybrané období ze session"""
    if not session.get("user_id"):
        return redirect("/login")

    stredisko = Stredisko.query.get_or_404(stredisko_id)
    if stredisko.user_id != session["user_id"]:
        return "Nepovolený přístup", 403

    try:
        # ✅ OPRAVA: Použij vybrané období ze session místo aktuálního data
        vybrane_obdobi = get_session_obdobi(stredisko_id)
        
        if not vybrane_obdobi:
            flash("❌ Není vybráno žádné období pro smazání výpočtů.")
            return redirect(url_for("fakturace.koncove_ceny", stredisko_id=stredisko_id))
        
        print(f"🗑️ DEBUG: Mažu výpočty pro období {vybrane_obdobi.rok}/{vybrane_obdobi.mesic:02d} (ID: {vybrane_obdobi.id})")
        
        # Smaž výpočty pro vybrané období a středisko
        smazano = VypocetOM.query.filter(VypocetOM.id.in_(
            db.session.query(VypocetOM.id)\
                .join(OdberneMisto)\
                .filter(OdberneMisto.stredisko_id == stredisko_id)\
                .filter(VypocetOM.obdobi_id == vybrane_obdobi.id)
        )).delete(synchronize_session=False)
        db.session.commit()
        
        if smazano > 0:
            flash(f"✅ Smazáno {smazano} výpočtů pro období {vybrane_obdobi.rok}/{vybrane_obdobi.mesic:02d}.")
        else:
            flash(f"⚠️ Pro období {vybrane_obdobi.rok}/{vybrane_obdobi.mesic:02d} nebyly nalezeny žádné výpočty k smazání.")

    except Exception as e:
        db.session.rollback()
        flash(f"❌ Chyba při mazání: {str(e)}")

    return redirect(url_for("fakturace.koncove_ceny", stredisko_id=stredisko_id))


@fakturace_bp.route("/<int:stredisko_id>/vygenerovat_html")
def vygenerovat_html(stredisko_id):
    if not session.get("user_id"):
        return redirect("/login")

    stredisko = Stredisko.query.get_or_404(stredisko_id)
    if stredisko.user_id != session["user_id"]:
        return "Nepovolený přístup", 403

    flash("HTML faktury byly (ne)úspěšně vygenerovány, funkce zatím není implementována.")
    return redirect(url_for("fakturace.fakturace", stredisko_id=stredisko_id))


@fakturace_bp.route("/<int:stredisko_id>/vygenerovat_pdf")
def vygenerovat_pdf(stredisko_id):
    if not session.get("user_id"):
        return redirect("/login")

    stredisko = Stredisko.query.get_or_404(stredisko_id)
    if stredisko.user_id != session["user_id"]:
        return "Nepovolený přístup", 403

    flash("PDF faktury byly (ne)úspěšně vygenerovány, funkce zatím není implementována.")
    return redirect(url_for("fakturace.fakturace", stredisko_id=stredisko_id))


@fakturace_bp.route("/<int:stredisko_id>/parametry")
def parametry_fakturace(stredisko_id):
    if not session.get("user_id"):
        return redirect("/login")

    stredisko = Stredisko.query.get_or_404(stredisko_id)
    if stredisko.user_id != session["user_id"]:
        return "Nepovolený přístup", 403

    # Získej všechna dostupná období pro středisko
    dostupna_obdobi = get_dostupna_obdobi_pro_stredisko(stredisko_id)
    
    # Zpracuj výběr období a ulož do session
    vybrane_obdobi = handle_obdobi_selection(stredisko_id, request.args)

    if not vybrane_obdobi:
        flash("❌ Žádné období fakturace nebylo nalezeno.")
        return redirect(url_for("strediska.spravovat_stredisko", stredisko_id=stredisko_id))

    # Načti základní údaje o faktuře a záloze podle vybraného období
    fak = Faktura.query.filter_by(stredisko_id=stredisko_id, obdobi_id=vybrane_obdobi.id).first()
    zal = ZalohovaFaktura.query.filter_by(stredisko_id=stredisko_id, obdobi_id=vybrane_obdobi.id).first()

    return render_template("fakturace/parametry_fakturace.html", 
                          stredisko=stredisko, 
                          vybrane_obdobi=vybrane_obdobi,
                          vsechna_obdobi=dostupna_obdobi,
                          fak=fak, 
                          zal=zal)


@fakturace_bp.route("/<int:stredisko_id>/ulozit_zalohu/<int:obdobi_id>", methods=["POST"])
def ulozit_zalohu(stredisko_id, obdobi_id):
    if not session.get("user_id"):
        return redirect("/login")

    stredisko = Stredisko.query.get_or_404(stredisko_id)
    if stredisko.user_id != session["user_id"]:
        return "Nepovolený přístup", 403

    # Ověř, že období patří střediska - ODSTRANĚN typ_obdobi
    obdobi = ObdobiFakturace.query.filter_by(
        id=obdobi_id, 
        stredisko_id=stredisko_id
    ).first()
    
    if not obdobi:
        flash("❌ Období nebylo nalezeno.")
        return redirect(url_for("fakturace.parametry_fakturace", stredisko_id=stredisko_id))

    # Najdi nebo vytvoř záznam zálohy
    zaloha = ZalohovaFaktura.query.filter_by(
        stredisko_id=stredisko_id, 
        obdobi_id=obdobi_id
    ).first()
    
    if not zaloha:
        zaloha = ZalohovaFaktura(stredisko_id=stredisko_id, obdobi_id=obdobi_id)

    # Ulož data z formuláře
    zaloha.cislo_zalohove_faktury = request.form.get("cislo_zalohy", "")
    zaloha.konstantni_symbol = request.form.get("konst_symbol", type=int)
    zaloha.variabilni_symbol = request.form.get("vs", type=int)
    
    # Zpracuj data
    splatnost = request.form.get("splatnost")
    if splatnost:
        from datetime import datetime
        zaloha.datum_splatnosti = datetime.strptime(splatnost, '%Y-%m-%d').date()
    
    vystaveni = request.form.get("vystaveni")
    if vystaveni:
        from datetime import datetime
        zaloha.datum_vystaveni = datetime.strptime(vystaveni, '%Y-%m-%d').date()
    
    zaloha.forma_uhrady = request.form.get("forma_uhrady", "")
    
    castka = request.form.get("castka_zalohy")
    if castka:
        zaloha.zaloha = float(castka)

    db.session.add(zaloha)
    db.session.commit()
    
    flash("✅ Zálohová faktura byla úspěšně uložena.")
    return redirect(url_for("fakturace.parametry_fakturace", stredisko_id=stredisko_id, obdobi_id=obdobi_id))

@fakturace_bp.route("/<int:stredisko_id>/upravit_dodavatele", methods=["POST"])
def upravit_dodavatele(stredisko_id):
    if not session.get("user_id"):
        return jsonify({"status": "error", "message": "Nepovolený přístup"}), 403

    stredisko = Stredisko.query.get_or_404(stredisko_id)
    if stredisko.user_id != session["user_id"]:
        return jsonify({"status": "error", "message": "Nepovolený přístup"}), 403

    try:
        field_name = request.form.get('name')
        new_value = request.form.get('value')

        dodavatel = InfoDodavatele.query.filter_by(stredisko_id=stredisko_id).first()
        if not dodavatel:
            dodavatel = InfoDodavatele(stredisko_id=stredisko_id)
            db.session.add(dodavatel)

        if hasattr(dodavatel, field_name):
            setattr(dodavatel, field_name, new_value)
            db.session.commit()
            return jsonify({"status": "success", "message": f"Pole {field_name} bylo úspěšně aktualizováno"})
        else:
            return jsonify({"status": "error", "message": f"Neznámé pole: {field_name}"}), 400

    except Exception as e:
        return jsonify({"status": "error", "message": f"Chyba při ukládání: {str(e)}"}), 500

@fakturace_bp.route("/<int:stredisko_id>/upravit_vystavovatele", methods=["POST"])
def upravit_vystavovatele(stredisko_id):
    if not session.get("user_id"):
        return jsonify({"status": "error", "message": "Nepovolený přístup"}), 403

    stredisko = Stredisko.query.get_or_404(stredisko_id)
    if stredisko.user_id != session["user_id"]:
        return jsonify({"status": "error", "message": "Nepovolený přístup"}), 403

    try:
        field_name = request.form.get('name')
        new_value = request.form.get('value')

        vystavovatel = InfoVystavovatele.query.filter_by(stredisko_id=stredisko_id).first()
        if not vystavovatel:
            vystavovatel = InfoVystavovatele(stredisko_id=stredisko_id)
            db.session.add(vystavovatel)

        if hasattr(vystavovatel, field_name):
            setattr(vystavovatel, field_name, new_value)
            db.session.commit()
            return jsonify({"status": "success", "message": f"Pole {field_name} bylo úspěšně aktualizováno"})
        else:
            return jsonify({"status": "error", "message": f"Neznámé pole: {field_name}"}), 400

    except Exception as e:
        return jsonify({"status": "error", "message": f"Chyba při ukládání: {str(e)}"}), 500

@fakturace_bp.route("/<int:stredisko_id>/upravit_odberatele", methods=["POST"])
def upravit_odberatele(stredisko_id):
    if not session.get("user_id"):
        return jsonify({"status": "error", "message": "Nepovolený přístup"}), 403

    stredisko = Stredisko.query.get_or_404(stredisko_id)
    if stredisko.user_id != session["user_id"]:
        return jsonify({"status": "error", "message": "Nepovolený přístup"}), 403

    try:
        field_name = request.form.get('name')
        new_value = request.form.get('value')

        odberatel = InfoOdberatele.query.filter_by(stredisko_id=stredisko_id).first()
        if not odberatel:
            odberatel = InfoOdberatele(stredisko_id=stredisko_id)
            db.session.add(odberatel)

        if hasattr(odberatel, field_name):
            setattr(odberatel, field_name, new_value)
            db.session.commit()
            return jsonify({"status": "success", "message": f"Pole {field_name} bylo úspěšně aktualizováno"})
        else:
            return jsonify({"status": "error", "message": f"Neznámé pole: {field_name}"}), 400

    except Exception as e:
        return jsonify({"status": "error", "message": f"Chyba při ukládání: {str(e)}"}), 500

@fakturace_bp.route("/<int:stredisko_id>/ulozit_fakturu/<int:obdobi_id>", methods=["POST"])
def ulozit_fakturu(stredisko_id, obdobi_id):
    if not session.get("user_id"):
        return redirect("/login")

    stredisko = Stredisko.query.get_or_404(stredisko_id)
    if stredisko.user_id != session["user_id"]:
        return "Nepovolený přístup", 403

    # Ověř, že období patří střediska - ODSTRANĚN typ_obdobi
    obdobi = ObdobiFakturace.query.filter_by(
        id=obdobi_id, 
        stredisko_id=stredisko_id
    ).first()
    
    if not obdobi:
        flash("❌ Období nebylo nalezeno.")
        return redirect(url_for("fakturace.parametry_fakturace", stredisko_id=stredisko_id))

    # Najdi nebo vytvoř záznam faktury
    faktura = Faktura.query.filter_by(
        stredisko_id=stredisko_id, 
        obdobi_id=obdobi_id
    ).first()
    
    if not faktura:
        faktura = Faktura(stredisko_id=stredisko_id, obdobi_id=obdobi_id)

    # Ulož data z formuláře
    # Převeď číslo faktury na integer (pokud není prázdné)
    cislo_str = request.form.get("cislo_faktury", "").strip()
    if cislo_str:
        try:
            faktura.cislo_faktury = int(cislo_str)
        except ValueError:
            flash("❌ Neplatné číslo faktury. Zadejte prosím číselnou hodnotu.")
            return redirect(url_for("fakturace.parametry_fakturace", stredisko_id=stredisko_id, obdobi_id=obdobi_id))
    else:
        faktura.cislo_faktury = None
    faktura.konstantni_symbol = request.form.get("konst_symbol_f", type=int)
    faktura.variabilni_symbol = request.form.get("vs_f", type=int)
    
    # Zpracuj data
    from datetime import datetime
    
    splatnost = request.form.get("splatnost_f")
    if splatnost:
        faktura.datum_splatnosti = datetime.strptime(splatnost, '%Y-%m-%d').date()
    
    vystaveni = request.form.get("vystaveni_f")
    if vystaveni:
        faktura.datum_vystaveni = datetime.strptime(vystaveni, '%Y-%m-%d').date()
        
    zdanitelne = request.form.get("zdanitelne_plneni")
    if zdanitelne:
        faktura.datum_zdanitelneho_plneni = datetime.strptime(zdanitelne, '%Y-%m-%d').date()
    
    od_date = request.form.get("od_date")
    if od_date:
        faktura.fakturace_od = datetime.strptime(od_date, '%Y-%m-%d').date()
        
    do_date = request.form.get("do_date")
    if do_date:
        faktura.fakturace_do = datetime.strptime(do_date, '%Y-%m-%d').date()
    
    faktura.forma_uhrady = request.form.get("forma_uhrady_f", "")
    faktura.popis_dodavky = request.form.get("popis", "")

    # Zpracuj checkbox pro fakturování jen distribuce
    faktura.fakturovat_jen_distribuci = bool(request.form.get("fakturovat_jen_distribuci"))

    dph = request.form.get("dph")
    if dph:
        faktura.sazba_dph = float(dph)

    db.session.add(faktura)
    db.session.commit()
    
    flash("✅ Faktura byla úspěšně uložena.")
    return redirect(url_for("fakturace.parametry_fakturace", stredisko_id=stredisko_id, obdobi_id=obdobi_id))


@fakturace_bp.route("/<int:stredisko_id>/predvyplnit_cislo_faktury", methods=["POST"])
def predvyplnit_cislo_faktury(stredisko_id):
    """
    API endpoint pro předvyplnění dalšího čísla faktury.
    Používá atomickou operaci s locking pro zabránění duplikátům.
    """
    if not session.get("user_id"):
        return jsonify({"success": False, "error": "Nejste přihlášeni"}), 401

    # Ověření vlastnictví střediska
    stredisko = Stredisko.query.get_or_404(stredisko_id)
    if stredisko.user_id != session["user_id"]:
        return jsonify({"success": False, "error": "Nepovolený přístup"}), 403

    try:
        user_id = session["user_id"]

        # Použij SELECT FOR UPDATE pro atomic increment
        # Pokud záznam neexistuje, vytvoř ho
        cisla_record = db.session.query(CislaFaktur).filter_by(
            user_id=user_id,
            typ_faktury='faktura'
        ).with_for_update().first()

        if not cisla_record:
            # Vytvoř nový záznam s výchozí hodnotou
            cisla_record = CislaFaktur(
                user_id=user_id,
                typ_faktury='faktura',
                aktualni_cislo=270325130
            )
            db.session.add(cisla_record)
            db.session.flush()  # Získej ID pro další operace

        # Increment čísla faktury
        nove_cislo = cisla_record.aktualni_cislo + 1

        # Kontrola, zda číslo už neexistuje v databázi
        # (double-check proti duplikátům)
        existujici_faktura = Faktura.query.filter_by(cislo_faktury=nove_cislo).first()
        if existujici_faktura:
            # Pokud číslo existuje, najdi nejbližší volné
            max_cislo = db.session.query(db.func.max(Faktura.cislo_faktury)).scalar() or nove_cislo
            nove_cislo = max(nove_cislo, max_cislo + 1)

        # Aktualizuj číslo v tabulce
        cisla_record.aktualni_cislo = nove_cislo
        cisla_record.updated_at = db.func.now()

        db.session.commit()

        # Vypočítej automatická data
        from datetime import datetime, timedelta
        import calendar

        dnes = datetime.now().date()

        # Datum vystavení = 15. den aktuálního měsíce
        datum_vystaveni_date = dnes.replace(day=15)
        datum_vystaveni = datum_vystaveni_date.strftime('%Y-%m-%d')

        # Datum splatnosti = dnes + 14 dní
        datum_splatnosti = (dnes + timedelta(days=14)).strftime('%Y-%m-%d')

        # Předchozí měsíc
        if dnes.month == 1:
            predchozi_mesic = 12
            predchozi_rok = dnes.year - 1
        else:
            predchozi_mesic = dnes.month - 1
            predchozi_rok = dnes.year

        # Fakturace od = první den předchozího měsíce
        fakturace_od = datetime(predchozi_rok, predchozi_mesic, 1).strftime('%Y-%m-%d')

        # Fakturace do = poslední den předchozího měsíce
        posledni_den = calendar.monthrange(predchozi_rok, predchozi_mesic)[1]
        fakturace_do = datetime(predchozi_rok, predchozi_mesic, posledni_den).strftime('%Y-%m-%d')

        # Datum zdanitelného plnění = poslední den předchozího měsíce (stejné jako fakturace_do)
        datum_zdanitelneho_plneni = fakturace_do

        return jsonify({
            "success": True,
            "cislo_faktury": nove_cislo,
            "variabilni_symbol": nove_cislo,  # Variabilní symbol = číslo faktury
            "datum_vystaveni": datum_vystaveni,
            "datum_splatnosti": datum_splatnosti,
            "datum_zdanitelneho_plneni": datum_zdanitelneho_plneni,
            "fakturace_od": fakturace_od,
            "fakturace_do": fakturace_do,
            "message": f"Předvyplněno číslo faktury: {nove_cislo} a všechna data"
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            "success": False,
            "error": f"Chyba při generování čísla faktury: {str(e)}"
        }), 500