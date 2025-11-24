-- Migrace: Přidání sloupce 'om_na_stranku' do tabulky 'faktura'
-- Tento sloupec určuje, zda se v PDF přílohách 1 a 2 má každé odběrné místo tisknout na novou stránku

-- Přidání sloupce om_na_stranku (boolean, default FALSE)
ALTER TABLE faktura ADD COLUMN om_na_stranku BOOLEAN DEFAULT FALSE;

-- Hotovo! Sloupec 'om_na_stranku' byl přidán do tabulky 'faktura'.
