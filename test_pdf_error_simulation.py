#!/usr/bin/env python3
# -*- coding: utf-8 -*-

def test_pdf_error_detection():
    """Test detekce PDF chyby"""
    
    # Simulace různých chyb které se mohou vyskytnout
    test_errors = [
        "PDF.__init__() takes 1 positional argument but 3 were given",
        "pypdf.PdfReader.__init__() takes 1 positional argument but 2 were given", 
        "PyPDF2.PdfReader.__init__() missing 1 required positional argument",
        "Something else error that should not trigger fallback"
    ]
    
    def detect_pdf_error(error_msg):
        """Stejná logika jako v opravené funkci"""
        error_msg = str(error_msg).lower()
        return ('pdf.__init__()' in error_msg and 'positional argument' in error_msg) or \
               ('pypdf' in error_msg) or ('pyPDF2' in error_msg)
    
    print("=== TEST DETEKCE PDF CHYB ===")
    for i, error in enumerate(test_errors, 1):
        should_trigger = detect_pdf_error(error)
        print(f"{i}. '{error[:50]}...' -> {'TRIGGER FALLBACK' if should_trigger else 'NO FALLBACK'}")
    
    # Test očekávaných výsledků
    expected = [True, True, True, False]
    actual = [detect_pdf_error(err) for err in test_errors]
    
    if actual == expected:
        print("\n✅ Všechny testy prošly!")
        return True
    else:
        print(f"\n❌ Test selhal! Očekáváno: {expected}, Aktuální: {actual}")
        return False

if __name__ == "__main__":
    test_pdf_error_detection()