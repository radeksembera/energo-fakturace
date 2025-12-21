-- Migrace: Přidání sloupce 'aktivni' do tabulky 'strediska'
-- Datum: 2025-12-20
-- Popis: Implementace soft delete pro střediska - místo mazání budou deaktivována

-- Přidání sloupce aktivni s defaultní hodnotou TRUE
ALTER TABLE strediska
ADD COLUMN aktivni BOOLEAN DEFAULT TRUE NOT NULL;

-- Nastavení všech existujících středisek jako aktivní
UPDATE strediska
SET aktivni = TRUE
WHERE aktivni IS NULL;

-- Kontrolní SELECT pro ověření migrace
SELECT id, nazev_strediska, aktivni FROM strediska;
