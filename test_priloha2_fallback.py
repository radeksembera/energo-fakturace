#!/usr/bin/env python3
# -*- coding: utf-8 -*-

def test_priloha2_reportlab_fallback():
    """Test ReportLab fallback pre prílohu 2"""
    try:
        # Import funkcie z routes
        import sys
        import os
        sys.path.append(os.path.dirname(os.path.abspath(__file__)))
        
        from routes.print import _generate_priloha2_pdf_reportlab
        
        # Vytvor fake objekty pre test
        class FakeStredisko:
            def __init__(self):
                self.nazev = "Test Středisko"
        
        class FakeObdobi:
            def __init__(self):
                self.rok = 2024
                self.mesic = 10
        
        class FakeFaktura:
            def __init__(self):
                self.cislo_faktury = "F202410001"
        
        class FakeDodavatel:
            def __init__(self):
                self.nazev = "Test Dodavatel"
                
        class FakeOM:
            def __init__(self, cislo):
                self.cislo_om = cislo
        
        # Vytvor test data
        stredisko = FakeStredisko()
        obdobi = FakeObdobi()
        faktura = FakeFaktura()
        dodavatel = FakeDodavatel()
        
        vypocty_data = []
        for i in range(5):
            vypocty_data.append({
                'om': FakeOM(f"OM{i+1:03d}"),
                'celkem_om': 1000.50 + i * 100,
                'spotreba_vt_mwh': 10.5 + i,
                'spotreba_nt_mwh': 5.2 + i * 0.5
            })
        
        print("[DEBUG] Spustam test ReportLab fallback pre prilohu 2...")
        
        # Zavolaj funkciu
        pdf_data = _generate_priloha2_pdf_reportlab(stredisko, obdobi, faktura, dodavatel, vypocty_data)
        
        print(f"[OK] ReportLab fallback pre prilohu 2 uspesny, velkost: {len(pdf_data)} bytov")
        
        # Uloz test PDF
        with open('test_priloha2_fallback.pdf', 'wb') as f:
            f.write(pdf_data)
        print("[OK] Test PDF ulozene ako 'test_priloha2_fallback.pdf'")
        
        return True
        
    except Exception as e:
        print(f"[ERROR] Test ReportLab fallback pre prilohu 2 selhal: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    test_priloha2_reportlab_fallback()