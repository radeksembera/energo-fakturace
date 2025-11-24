-- Migrace: Přidání sloupců 'dofakturace' a 'slevovy_bonus' do tabulky 'vypocty_om'
-- Tyto sloupce budou obsahovat hodnoty z odečtů a ovlivňovat výpočet základu bez DPH

-- Přidání sloupce dofakturace
ALTER TABLE vypocty_om ADD COLUMN dofakturace NUMERIC;

-- Přidání sloupce slevovy_bonus
ALTER TABLE vypocty_om ADD COLUMN slevovy_bonus NUMERIC;

-- Hotovo! Sloupce 'dofakturace' a 'slevovy_bonus' byly přidány do tabulky 'vypocty_om'.
