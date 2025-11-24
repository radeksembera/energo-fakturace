-- Migrace: Odstranění sloupce 'priznak' z tabulky 'odecty'
-- SQLite nepodporuje DROP COLUMN přímo, proto vytvoříme novou tabulku

-- 1. Vytvoř novou tabulku bez sloupce priznak
CREATE TABLE odecty_new (
    id INTEGER PRIMARY KEY,
    stredisko_id INTEGER REFERENCES strediska(id),
    obdobi_id INTEGER REFERENCES obdobi_fakturace(id),
    oznaceni TEXT,
    zacatek_periody_mereni DATE,
    konec_periody_mereni DATE,
    pocatecni_hodnota_vt NUMERIC,
    hodnota_odectu_vt NUMERIC,
    spotreba_vt NUMERIC,
    pocatecni_hodnota_nt NUMERIC,
    hodnota_odectu_nt NUMERIC,
    spotreba_nt NUMERIC,
    dofakturace NUMERIC,
    slevovy_bonus NUMERIC
);

-- 2. Zkopíruj data ze staré tabulky (bez sloupce priznak)
INSERT INTO odecty_new (
    id, stredisko_id, obdobi_id, oznaceni,
    zacatek_periody_mereni, konec_periody_mereni,
    pocatecni_hodnota_vt, hodnota_odectu_vt, spotreba_vt,
    pocatecni_hodnota_nt, hodnota_odectu_nt, spotreba_nt,
    dofakturace, slevovy_bonus
)
SELECT
    id, stredisko_id, obdobi_id, oznaceni,
    zacatek_periody_mereni, konec_periody_mereni,
    pocatecni_hodnota_vt, hodnota_odectu_vt, spotreba_vt,
    pocatecni_hodnota_nt, hodnota_odectu_nt, spotreba_nt,
    dofakturace, slevovy_bonus
FROM odecty;

-- 3. Smaž starou tabulku
DROP TABLE odecty;

-- 4. Přejmenuj novou tabulku
ALTER TABLE odecty_new RENAME TO odecty;

-- Hotovo! Sloupec 'priznak' byl odstraněn z tabulky 'odecty'.
-- Sloupec 'priznak' zůstává v tabulce 'import_odectu'.
