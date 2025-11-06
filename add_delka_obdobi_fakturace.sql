-- Přidání sloupce delka_obdobi_fakturace do tabulky vypocty_om
-- Tento sloupec uchovává poměr období fakturace (1.0 = celý měsíc, 0.484 = 15/31 dní atd.)

ALTER TABLE vypocty_om
ADD COLUMN IF NOT EXISTS delka_obdobi_fakturace NUMERIC;

-- Nastavení výchozí hodnoty 1.0 pro existující záznamy
UPDATE vypocty_om
SET delka_obdobi_fakturace = 1.0
WHERE delka_obdobi_fakturace IS NULL;

-- Ověření změny
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name = 'vypocty_om' AND column_name = 'delka_obdobi_fakturace';
