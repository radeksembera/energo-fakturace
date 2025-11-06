from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

# Inicializace SQLAlchemy
db = SQLAlchemy()

# --- USERS ---
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.Text, unique=True, nullable=False)
    password_hash = db.Column(db.Text, nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)

    strediska = db.relationship('Stredisko', backref='user', cascade="all, delete")

# --- CENY ---
class CenaDistribuce(db.Model):
    __tablename__ = 'ceny_distribuce'
    id = db.Column(db.Integer, primary_key=True)
    stredisko_id = db.Column(db.Integer, db.ForeignKey('strediska.id'))
    distribuce = db.Column(db.Text)
    sazba = db.Column(db.Text)
    jistic = db.Column(db.Text)
    rok = db.Column(db.Integer)
    platba_za_jistic = db.Column(db.Numeric)
    platba_za_distribuci_vt = db.Column(db.Numeric)
    platba_za_distribuci_nt = db.Column(db.Numeric)
    systemove_sluzby = db.Column(db.Numeric)
    poze_dle_jistice = db.Column(db.Numeric)
    poze_dle_spotreby = db.Column(db.Numeric)
    nesitova_infrastruktura = db.Column(db.Numeric)
    dan_z_elektriny = db.Column(db.Numeric)

class CenaDodavatel(db.Model):
    __tablename__ = 'ceny_dodavatel'
    id = db.Column(db.Integer, primary_key=True)
    stredisko_id = db.Column(db.Integer, db.ForeignKey('strediska.id'))
    obdobi_id = db.Column(db.Integer, db.ForeignKey('obdobi_fakturace.id'))
    distribuce = db.Column(db.Text)
    sazba = db.Column(db.Text)
    platba_za_elektrinu_vt = db.Column(db.Numeric)
    platba_za_elektrinu_nt = db.Column(db.Numeric)
    mesicni_plat = db.Column(db.Numeric)

# --- INFO ---
class InfoDodavatele(db.Model):
    __tablename__ = 'info_dodavatele'
    id = db.Column(db.Integer, primary_key=True)
    stredisko_id = db.Column(db.Integer, db.ForeignKey('strediska.id'))
    nazev_sro = db.Column(db.Text)
    adresa_radek_1 = db.Column(db.Text)
    adresa_radek_2 = db.Column(db.Text)
    ico_sro = db.Column(db.Text)
    dic_sro = db.Column(db.Text)
    zapis_u_soudu = db.Column(db.Text)
    banka = db.Column(db.Text)
    cislo_uctu = db.Column(db.Text)
    swift = db.Column(db.Text)
    iban = db.Column(db.Text)

class InfoVystavovatele(db.Model):
    __tablename__ = 'info_vystavovatele'
    id = db.Column(db.Integer, primary_key=True)
    stredisko_id = db.Column(db.Integer, db.ForeignKey('strediska.id'))
    jmeno_vystavitele = db.Column(db.Text)
    telefon_vystavitele = db.Column(db.Text)
    email_vystavitele = db.Column(db.Text)

class InfoOdberatele(db.Model):
    __tablename__ = 'info_odberatele'
    id = db.Column(db.Integer, primary_key=True)
    stredisko_id = db.Column(db.Integer, db.ForeignKey('strediska.id'))
    nazev_sro = db.Column(db.Text)
    adresa_radek_1 = db.Column(db.Text)
    adresa_radek_2 = db.Column(db.Text)
    ico_sro = db.Column(db.Text)
    dic_sro = db.Column(db.Text)

# --- STREDISKA ---
class Stredisko(db.Model):
    __tablename__ = 'strediska'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    nazev_strediska = db.Column(db.Text)
    adresa = db.Column(db.Text)
    misto = db.Column(db.Text)
    stredisko = db.Column(db.Text)
    stredisko_mail = db.Column(db.Text)
    distribuce = db.Column(db.Text)
    poznamka = db.Column(db.Text)
    nazev_faktury = db.Column(db.Text)
    role = db.Column(db.Text, nullable=False)

    odberna_mista = db.relationship('OdberneMisto', backref='stredisko', cascade="all, delete")
    odecty = db.relationship('Odečet', backref='stredisko', cascade="all, delete")
    importy = db.relationship('ImportOdečtu', backref='stredisko', cascade="all, delete")
    faktury = db.relationship('Faktura', backref='stredisko', cascade="all, delete")
    zaloha_faktury = db.relationship('ZalohovaFaktura', backref='stredisko', cascade="all, delete")
    info_dodavatele = db.relationship('InfoDodavatele', backref='stredisko', cascade="all, delete")
    info_vystavovatele = db.relationship('InfoVystavovatele', backref='stredisko', cascade="all, delete")
    info_odberatele = db.relationship('InfoOdberatele', backref='stredisko', cascade="all, delete")

# --- ODBERNA MISTA ---
class OdberneMisto(db.Model):
    __tablename__ = 'odberna_mista'
    id = db.Column(db.Integer, primary_key=True)
    stredisko_id = db.Column(db.Integer, db.ForeignKey('strediska.id'))
    cislo_om = db.Column(db.Text)
    ean_om = db.Column(db.Text)
    nazev_om = db.Column(db.Text)
    distribucni_sazba_om = db.Column(db.Text)
    kategorie_jistice_om = db.Column(db.Text)
    hodnota_jistice_om = db.Column(db.Text)
    poznamka_om = db.Column(db.Text)

    vypocty = db.relationship('VypocetOM', backref='odberne_misto', cascade="all, delete")

# --- VYPOCTY ---
class VypocetOM(db.Model):
    __tablename__ = 'vypocty_om'
    id = db.Column(db.Integer, primary_key=True)
    odberne_misto_id = db.Column(db.Integer, db.ForeignKey('odberna_mista.id'))
    obdobi_id = db.Column(db.Integer, db.ForeignKey('obdobi_fakturace.id'))
    delka_obdobi_fakturace = db.Column(db.Numeric)  # Poměr období fakturace
    platba_za_jistic = db.Column(db.Numeric)
    platba_za_distribuci_vt = db.Column(db.Numeric)
    platba_za_distribuci_nt = db.Column(db.Numeric)
    systemove_sluzby = db.Column(db.Numeric)
    poze_dle_jistice = db.Column(db.Numeric)
    poze_dle_spotreby = db.Column(db.Numeric)
    nesitova_infrastruktura = db.Column(db.Numeric)
    dan_z_elektriny = db.Column(db.Numeric)
    platba_za_elektrinu_vt = db.Column(db.Numeric)
    platba_za_elektrinu_nt = db.Column(db.Numeric)
    mesicni_plat = db.Column(db.Numeric)
    zaklad_bez_dph = db.Column(db.Numeric)
    castka_dph = db.Column(db.Numeric)
    celkem_vc_dph = db.Column(db.Numeric)

    # Výpočty bez distribuce
    zaklad_bez_dph_bez_di = db.Column(db.Numeric)
    castka_dph_bez_di = db.Column(db.Numeric)
    celkem_vc_dph_bez_di = db.Column(db.Numeric)

# --- ODECTY ---
class Odečet(db.Model):
    __tablename__ = 'odecty'
    id = db.Column(db.Integer, primary_key=True)
    stredisko_id = db.Column(db.Integer, db.ForeignKey('strediska.id'))
    # Přidáno období_id pro jednotnou správu
    obdobi_id = db.Column(db.Integer, db.ForeignKey('obdobi_fakturace.id'))
    oznaceni = db.Column(db.Text)
    zacatek_periody_mereni = db.Column(db.Date)
    konec_periody_mereni = db.Column(db.Date)
    pocatecni_hodnota_vt = db.Column(db.Numeric)
    hodnota_odectu_vt = db.Column(db.Numeric)
    spotreba_vt = db.Column(db.Numeric)
    pocatecni_hodnota_nt = db.Column(db.Numeric)
    hodnota_odectu_nt = db.Column(db.Numeric)
    spotreba_nt = db.Column(db.Numeric)
    dofakturace = db.Column(db.Numeric)
    slevovy_bonus = db.Column(db.Numeric)
    priznak = db.Column(db.Text)

# --- IMPORT ODECTU ---
class ImportOdečtu(db.Model):
    __tablename__ = 'import_odectu'
    id = db.Column(db.Integer, primary_key=True)
    stredisko_id = db.Column(db.Integer, db.ForeignKey('strediska.id'))
    # Přidáno období_id pro jednotnou správu
    obdobi_id = db.Column(db.Integer, db.ForeignKey('obdobi_fakturace.id'))
    oznaceni_om = db.Column(db.Text)
    # Zachováme rok/měsíc z importovaných dat
    import_rok = db.Column(db.Integer)
    import_mesic = db.Column(db.Integer)
    nazev = db.Column(db.Text)
    textova_informace = db.Column(db.Text)
    zacatek_periody_mereni = db.Column(db.Date)
    konec_periody_mereni = db.Column(db.Date)
    datum_a_cas_odectu = db.Column(db.DateTime)
    zdroj_hodnoty = db.Column(db.Text)
    popis_dimenze = db.Column(db.Text)
    pocatecni_hodnota = db.Column(db.Numeric)
    hodnota_odectu = db.Column(db.Numeric)
    spotreba = db.Column(db.Numeric)
    merna_jednotka = db.Column(db.Text)
    dofakturace = db.Column(db.Numeric)
    slevovy_bonus = db.Column(db.Numeric)
    zaloha_importu_kc = db.Column(db.Numeric)
    priznak = db.Column(db.Text)

# --- ZALOHOVA FAKTURA ---
class ZalohovaFaktura(db.Model):
    __tablename__ = 'zalohova_faktura'
    id = db.Column(db.Integer, primary_key=True)
    stredisko_id = db.Column(db.Integer, db.ForeignKey('strediska.id'))
    # Přidáno období_id pro jednotnou správu
    obdobi_id = db.Column(db.Integer, db.ForeignKey('obdobi_fakturace.id'))
    cislo_zalohove_faktury = db.Column(db.Text)
    konstantni_symbol = db.Column(db.Text)
    variabilni_symbol = db.Column(db.Text)
    datum_splatnosti = db.Column(db.Date)
    forma_uhrady = db.Column(db.Text)
    datum_vystaveni = db.Column(db.Date)
    zaloha = db.Column(db.Numeric)

# --- FAKTURA ---
class Faktura(db.Model):
    __tablename__ = 'faktura'
    id = db.Column(db.Integer, primary_key=True)
    stredisko_id = db.Column(db.Integer, db.ForeignKey('strediska.id'))
    # Přidáno období_id pro jednotnou správu
    obdobi_id = db.Column(db.Integer, db.ForeignKey('obdobi_fakturace.id'))
    cislo_faktury = db.Column(db.BigInteger)
    variabilni_symbol = db.Column(db.Text)
    konstantni_symbol = db.Column(db.Text)
    datum_splatnosti = db.Column(db.Date)
    datum_vystaveni = db.Column(db.Date)
    datum_zdanitelneho_plneni = db.Column(db.Date)
    forma_uhrady = db.Column(db.Text)
    popis_dodavky = db.Column(db.Text)
    sazba_dph = db.Column(db.Numeric)
    fakturace_od = db.Column(db.Date)
    fakturace_do = db.Column(db.Date)
    fakturovat_jen_distribuci = db.Column(db.Boolean, default=False, nullable=False)

# --- CISLA FAKTUR ---
class CislaFaktur(db.Model):
    __tablename__ = 'cisla_faktur'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    typ_faktury = db.Column(db.String(20), nullable=False, default='faktura')
    aktualni_cislo = db.Column(db.BigInteger, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'typ_faktury', name='unique_user_typ_faktury'),
    )

# --- OBDOBI FAKTURACE ---
class ObdobiFakturace(db.Model):
    __tablename__ = 'obdobi_fakturace'
    id = db.Column(db.Integer, primary_key=True)
    stredisko_id = db.Column(db.Integer, db.ForeignKey('strediska.id'))
    rok = db.Column(db.Integer, nullable=False)
    mesic = db.Column(db.Integer, nullable=False)
    # Odstranil jsem nazev, stav a created_at - nejsou v existující tabulce
