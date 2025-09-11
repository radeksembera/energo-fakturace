#!/usr/bin/env python3
# -*- coding: utf-8 -*-

def test_nova_priloha2_reportlab():
    """Test nove funkcie priloha 2 - ciste ReportLab ako priloha 1"""
    try:
        # Import funkcii z routes
        import sys
        import os
        sys.path.append(os.path.dirname(os.path.abspath(__file__)))
        
        from routes.print import _generate_priloha2_pdf_reportlab
        
        # Vytvor fake objekty pre test
        class FakeStredisko:
            def __init__(self):
                self.nazev = "Test Stredisko"
        
        class FakeObdobi:
            def __init__(self):
                self.rok = 2024
                self.mesic = 10
        
        class FakeFaktura:
            def __init__(self):
                self.cislo_faktury = "F202410001"
                self.sazba_dph = 21
        
        class FakeDodavatel:
            def __init__(self):
                self.nazev_sro = "Test Dodavatel s.r.o."
                self.adresa_radek_1 = "Test ulice 123"
                self.adresa_radek_2 = "12345 Test mesto"
                self.dic_sro = "CZ12345678"
                self.ico_sro = "12345678"
                
        class FakeOM:
            def __init__(self, cislo):
                self.cislo_om = cislo
                
        class FakeVypocet:
            def __init__(self):
                self.mesicni_plat = 100.0
                self.platba_za_elektrinu_vt = 500.0
                self.platba_za_elektrinu_nt = 300.0
                self.platba_za_jistic = 50.0
                self.platba_za_distribuci_vt = 200.0
                self.platba_za_distribuci_nt = 150.0
                self.systemove_sluzby = 75.0
                self.poze_dle_jistice = 80.0
                self.poze_dle_spotreby = 90.0
                self.nesitova_infrastruktura = 25.0
                self.dan_z_elektriny = 30.0
        
        # Vytvor test data
        stredisko = FakeStredisko()
        obdobi = FakeObdobi()
        faktura = FakeFaktura()
        dodavatel = FakeDodavatel()
        
        vypocty_om = []
        for i in range(3):
            vypocty_om.append((FakeVypocet(), FakeOM(f"OM{i+1:03d}")))
        
        print("[DEBUG] Spustam test novej prilohy 2 - cisty ReportLab...")
        
        # Zavolaj funkciu
        pdf_data = _generate_priloha2_pdf_reportlab(stredisko, obdobi, faktura, dodavatel, vypocty_om)
        
        print(f"[OK] Nova priloha 2 (cisty ReportLab) uspesna, velkost: {len(pdf_data)} bytov")
        
        # Uloz test PDF
        with open('test_nova_priloha2.pdf', 'wb') as f:
            f.write(pdf_data)
        print("[OK] Test PDF ulozene ako 'test_nova_priloha2.pdf'")
        
        return True
        
    except Exception as e:
        print(f"[ERROR] Test novej prilohy 2 selhal: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    test_nova_priloha2_reportlab()