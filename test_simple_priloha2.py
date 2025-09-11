#!/usr/bin/env python3
# -*- coding: utf-8 -*-

def create_simple_priloha2_pdf():
    """Vytvori jednoduchy PDF test pre prilohu 2"""
    try:
        from reportlab.platypus import SimpleDocTemplate, Paragraph
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.pagesizes import A4
        import io
        
        # Vytvor PDF buffer
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        
        # Vytvor story
        story = []
        styles = getSampleStyleSheet()
        
        story.append(Paragraph("TEST PRILOHA 2", styles['Title']))
        story.append(Paragraph("Toto je testovaci PDF pre prilohu 2.", styles['Normal']))
        story.append(Paragraph("Ak vidite toto, PDF generovanie funguje.", styles['Normal']))
        
        # Vygeneruj PDF
        doc.build(story)
        pdf_data = buffer.getvalue()
        buffer.close()
        
        print(f"[OK] Jednoduchy test PDF vytvoreny, velkost: {len(pdf_data)} bytov")
        
        # Uloz
        with open('test_simple_priloha2.pdf', 'wb') as f:
            f.write(pdf_data)
        print("[OK] Test PDF ulozeny ako 'test_simple_priloha2.pdf'")
        
        return pdf_data
        
    except Exception as e:
        print(f"[ERROR] Jednoduchy test PDF selhal: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    create_simple_priloha2_pdf()