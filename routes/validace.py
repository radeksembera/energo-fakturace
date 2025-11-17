# -*- coding: utf-8 -*-
"""
Validace routes - validace dat v systému
"""

from flask import Blueprint, render_template, session, redirect, url_for, flash, request, jsonify
from models import db, Stredisko, VypocetOM, OdberneMisto, ObdobiFakturace, SpotrebaHlavnihoJistice, SumarizaceStrediska
from sqlalchemy import func
from decimal import Decimal

validace_bp = Blueprint('validace', __name__, url_prefix='/validace')

# Definice projektů a kódů středisek
# Každý projekt může mít jeden nebo více kódů středisek (seznam)
VALIDACNI_PROJEKTY = [
    {"projekt": "LDS Coral Office Park, budova A", "kody": ["0001"]},
    {"projekt": "LDS Coral Office Park, budova B", "kody": ["0002"]},
    {"projekt": "LDS Coral Office Park, budova C", "kody": ["0003"]},
    {"projekt": "LDS Coral Office Park, budova D a F", "kody": ["0004", "0014"]},
    {"projekt": "Budova FOC", "kody": ["0009"]},
    {"projekt": "BREDA & WEINSTEIN a.s.", "kody": ["0005", "0006"]},
]

@validace_bp.route('/')
def index():
    """Zobrazí stránku validace"""
    if not session.get("user_id"):
        return redirect(url_for("auth.login"))

    user_id = session["user_id"]

    # Načti všechna střediska uživatele
    strediska = Stredisko.query.filter_by(user_id=user_id).all()

    if not strediska:
        flash("❌ Nemáte vytvořena žádná střediska.", "warning")
        return redirect(url_for("strediska.strediska"))

    # Načti všechna dostupná období
    obdobi_list = ObdobiFakturace.query\
        .join(Stredisko)\
        .filter(Stredisko.user_id == user_id)\
        .order_by(ObdobiFakturace.rok.desc(), ObdobiFakturace.mesic.desc())\
        .distinct(ObdobiFakturace.rok, ObdobiFakturace.mesic)\
        .all()

    # Vyber období z parametru nebo první dostupné
    vybrane_obdobi = None
    if request.args.get('rok') and request.args.get('mesic'):
        rok = int(request.args.get('rok'))
        mesic = int(request.args.get('mesic'))
        vybrane_obdobi = {'rok': rok, 'mesic': mesic}
    elif obdobi_list:
        vybrane_obdobi = {'rok': obdobi_list[0].rok, 'mesic': obdobi_list[0].mesic}

    # Připrav data pro tabulku hlavních jističů
    data_hlavnich_jisticu = []
    if vybrane_obdobi:
        for item in VALIDACNI_PROJEKTY:
            kody = item['kody']
            projekt = item['projekt']

            # Vytvoř kombinovaný klíč pro ukládání do databáze
            kombinovany_kod = ";".join(kody)

            # Sečti spotřebu hlavního jističe ze všech kódů
            # Nejdřív zkus najít záznam s kombinovaným kódem
            spotreba_hlavni = SpotrebaHlavnihoJistice.query.filter_by(
                kod_strediska=kombinovany_kod,
                rok=vybrane_obdobi['rok'],
                mesic=vybrane_obdobi['mesic']
            ).first()

            # Pokud neexistuje, sečti jednotlivé kódy
            if spotreba_hlavni:
                spotreba_hlavni_mwh = float(spotreba_hlavni.spotreba_mwh)
            else:
                spotreba_hlavni_mwh = 0.0
                for kod in kody:
                    spotreba = SpotrebaHlavnihoJistice.query.filter_by(
                        kod_strediska=kod,
                        rok=vybrane_obdobi['rok'],
                        mesic=vybrane_obdobi['mesic']
                    ).first()
                    if spotreba:
                        spotreba_hlavni_mwh += float(spotreba.spotreba_mwh)

            # Sečti spotřebu podružných elektroměrů ze všech středisek s danými kódy
            spotreba_podruzne_kwh = 0.0
            for kod in kody:
                # Najdi středisko s daným kódem
                stredisko = Stredisko.query.filter_by(stredisko=kod, user_id=user_id).first()

                if stredisko:
                    # Najdi období pro toto středisko
                    obdobi = ObdobiFakturace.query.filter_by(
                        stredisko_id=stredisko.id,
                        rok=vybrane_obdobi['rok'],
                        mesic=vybrane_obdobi['mesic']
                    ).first()

                    if obdobi:
                        # Sečti spotřeby všech odběrných míst
                        suma = db.session.query(func.sum(VypocetOM.spotreba_om))\
                            .join(OdberneMisto)\
                            .filter(
                                OdberneMisto.stredisko_id == stredisko.id,
                                VypocetOM.obdobi_id == obdobi.id
                            ).scalar()

                        if suma:
                            spotreba_podruzne_kwh += float(suma)

            # Převeď na MWh
            spotreba_podruzne_mwh = spotreba_podruzne_kwh / 1000.0

            # Vypočítej rozdíl (Spotřeba podružné elektroměry - Spotřeba hlavní jistič)
            rozdil = spotreba_podruzne_mwh - spotreba_hlavni_mwh

            data_hlavnich_jisticu.append({
                'projekt': projekt,
                'kody': kody,
                'kombinovany_kod': kombinovany_kod,
                'spotreba_hlavni_mwh': spotreba_hlavni_mwh,
                'spotreba_podruzne_mwh': spotreba_podruzne_mwh,
                'rozdil': rozdil
            })

    # Připrav data pro druhý blok "Střediska"
    # Vyber středisko z parametru nebo první dostupné
    vybrane_stredisko_id = request.args.get('stredisko_id', type=int)
    if not vybrane_stredisko_id and strediska:
        vybrane_stredisko_id = strediska[0].id

    # Definuj období pro zobrazení: 07/2025 až 07/2026
    obdobi_mesice = [
        (2025, 7), (2025, 8), (2025, 9), (2025, 10), (2025, 11), (2025, 12),
        (2026, 1), (2026, 2), (2026, 3), (2026, 4), (2026, 5), (2026, 6), (2026, 7)
    ]

    # Načti data pro vybrané středisko
    data_strediska = []
    if vybrane_stredisko_id:
        for rok, mesic in obdobi_mesice:
            # Najdi období
            obdobi = ObdobiFakturace.query.filter_by(
                stredisko_id=vybrane_stredisko_id,
                rok=rok,
                mesic=mesic
            ).first()

            if obdobi:
                # Načti sumarizaci
                sumarizace = SumarizaceStrediska.query.filter_by(
                    stredisko_id=vybrane_stredisko_id,
                    obdobi_id=obdobi.id
                ).first()

                if sumarizace:
                    data_strediska.append({
                        'rok': rok,
                        'mesic': mesic,
                        'celkova_spotreba': float(sumarizace.celkova_spotreba),
                        'celkova_cena_s_dph': float(sumarizace.celkova_cena_s_dph)
                    })
                else:
                    # Období existuje, ale není sumarizace
                    data_strediska.append({
                        'rok': rok,
                        'mesic': mesic,
                        'celkova_spotreba': None,
                        'celkova_cena_s_dph': None
                    })
            else:
                # Období neexistuje
                data_strediska.append({
                    'rok': rok,
                    'mesic': mesic,
                    'celkova_spotreba': None,
                    'celkova_cena_s_dph': None
                })

    return render_template('validace.html',
                         obdobi_list=obdobi_list,
                         vybrane_obdobi=vybrane_obdobi,
                         data_hlavnich_jisticu=data_hlavnich_jisticu,
                         strediska=strediska,
                         vybrane_stredisko_id=vybrane_stredisko_id,
                         data_strediska=data_strediska)


@validace_bp.route('/ulozit_spotrebu', methods=['POST'])
def ulozit_spotrebu():
    """Uloží spotřebu hlavního jističe"""
    if not session.get("user_id"):
        return jsonify({'success': False, 'error': 'Nepřihlášen'}), 401

    try:
        kod_strediska = request.json.get('kod_strediska')
        rok = int(request.json.get('rok'))
        mesic = int(request.json.get('mesic'))
        spotreba_mwh = float(request.json.get('spotreba_mwh', 0))

        # Najdi nebo vytvoř záznam
        spotreba = SpotrebaHlavnihoJistice.query.filter_by(
            kod_strediska=kod_strediska,
            rok=rok,
            mesic=mesic
        ).first()

        if not spotreba:
            spotreba = SpotrebaHlavnihoJistice(
                kod_strediska=kod_strediska,
                rok=rok,
                mesic=mesic
            )

        spotreba.spotreba_mwh = Decimal(str(spotreba_mwh))

        db.session.add(spotreba)
        db.session.commit()

        return jsonify({'success': True, 'spotreba_mwh': spotreba_mwh})

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
