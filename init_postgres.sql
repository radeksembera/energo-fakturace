CREATE TABLE users (
  id TEXT,
  username TEXT,
  password_hash TEXT,
  role TEXT
);

CREATE TABLE strediska (
  id TEXT,
  user_id TEXT,
  nazev_strediska TEXT,
  adresa TEXT,
  misto TEXT,
  stredisko TEXT,
  stredisko_mail TEXT,
  distribuce TEXT,
  poznamka TEXT
);

CREATE TABLE ceny_distribuce (
  id TEXT,
  distribuce TEXT,
  sazba TEXT,
  jistic TEXT,
  platba_za_jistic TEXT,
  platba_za_distribuci_vt TEXT,
  platba_za_distribuci_nt TEXT,
  systemove_sluzby TEXT,
  poze_dle_jistice TEXT,
  poze_dle_spotreby TEXT,
  nesitova_infrastruktura TEXT,
  dan_z_elektriny TEXT
);

CREATE TABLE ceny_dodavatel (
  id TEXT,
  distribuce TEXT,
  sazba TEXT,
  jistic TEXT,
  platba_za_elektrinu_vt TEXT,
  platba_za_elektrinu_nt TEXT,
  mesicni_plat TEXT
);

CREATE TABLE info_dodavatele (
  id TEXT,
  nazev_sro TEXT,
  adresa_radek_1 TEXT,
  adresa_radek_2 TEXT,
  ico_sro TEXT,
  dic_sro TEXT,
  zapis_u_soudu TEXT,
  banka TEXT,
  cislo_uctu TEXT,
  swift TEXT,
  iban TEXT
);

CREATE TABLE info_vystavovatele (
  id TEXT,
  jmeno_vystavitele TEXT,
  telefon_vystavitele TEXT,
  email_vystavitele TEXT
);

CREATE TABLE info_odberatele (
  id TEXT,
  nazev_sro TEXT,
  adresa_radek_1 TEXT,
  adresa_radek_2 TEXT,
  ico_sro TEXT,
  dic_sro TEXT
);

CREATE TABLE odberna_mista (
  id TEXT,
  cislo_om TEXT,
  ean_om TEXT,
  nazev_om TEXT,
  distribucni_sazba_om TEXT,
  kategorie_jistice_om TEXT,
  hodnota_jistice_om TEXT,
  poznamka_om TEXT
);

CREATE TABLE zalohova_faktura (
  id TEXT,
  rok TEXT,
  mesic TEXT,
  cislo_zalohove_faktury TEXT,
  konstantni_symbol TEXT,
  variabilni_symbol TEXT,
  datum_splatnosti TEXT,
  forma_uhrady TEXT,
  datum_vystaveni TEXT,
  zaloha TEXT
);

CREATE TABLE faktura (
  id TEXT,
  rok TEXT,
  mesic TEXT,
  císlo_faktury TEXT,
  konstantni_symbol TEXT,
  datum_splatnosti TEXT,
  datum_vystaveni TEXT,
  datum_zdanitelneho_pIneni TEXT,
  forma_uhrady TEXT,
  popis_dodavky TEXT,
  sazba_dph TEXT,
  fakturace_od TEXT,
  fakturace_do TEXT
);

CREATE TABLE odecty (
  id TEXT,
  oznaceni TEXT,
  rok TEXT,
  mesic TEXT,
  zacatek_periody_mereni TEXT,
  konec_periody_mereni TEXT,
  pocatecni_hodnota_vt TEXT,
  hodnota_odectu_vt TEXT,
  spotreba_vt TEXT,
  pocatecni_hodnota_nt TEXT,
  hodnota_odectu_nt TEXT,
  spotreba_nt TEXT,
  dofakturace TEXT,
  slevovy_bonus TEXT,
  priznak TEXT
);

CREATE TABLE import_odectu (
  id TEXT,
  oznaceni_om TEXT,
  rok TEXT,
  mesic TEXT,
  nazev TEXT,
  textova_informace TEXT,
  zacatek_periody_mereni TEXT,
  konec_periody_mereni TEXT,
  datum_a_cas_odectu TEXT,
  zdroj_hodnoty TEXT,
  popis_dimenze TEXT,
  pocatecni_hodnota TEXT,
  hodnota_odectu TEXT,
  spotreba TEXT,
  merna_jednotka TEXT,
  dofakturace TEXT,
  slevovy_bonus TEXT,
  zaloha_importu_kc TEXT,
  priznak TEXT
);

CREATE TABLE vypocty_om (
  id TEXT,
  platba_za_jistic TEXT,
  platba_za_distribuci_vt TEXT,
  platba_za_distribuci_nt TEXT,
  systemove_sluzby TEXT,
  poze_dle_jistice TEXT,
  poze_dle_spotreby TEXT,
  nesitova_infrastruktura TEXT,
  dan_z_elektriny TEXT,
  platba_za_elektrinu_vt TEXT,
  platba_za_elektrinu_nt TEXT,
  mesicni_plat TEXT,
  platba_za_jistic TEXT,
  platba_za_distribuci_vt TEXT,
  platba_za_distribuci_nt TEXT,
  systemove_sluzby TEXT,
  poze_dle_jistice TEXT,
  poze_dle_spotreby TEXT,
  poze_min TEXT,
  nesitova_infrastruktura TEXT,
  dan_z_elektriny TEXT,
  platba_za_elektrinu_vt TEXT,
  platba_za_elektrinu_nt TEXT,
  mesicni_plat TEXT,
  zaklad_bez_dph TEXT,
  castka_dph TEXT,
  celkem_vc_dph TEXT
);

