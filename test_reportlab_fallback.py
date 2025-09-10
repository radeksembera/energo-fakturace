#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
import io

def test_reportlab_fallback():
    """Test funkce pro ReportLab fallback"""
    try:
        print("[DEBUG] Testovani ReportLab fallback...")
        
        # Vytvoř PDF dokument
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, 
                              rightMargin=20*mm, leftMargin=20*mm,
                              topMargin=20*mm, bottomMargin=20*mm)
        
        story = []
        styles = getSampleStyleSheet()
        
        # Nadpis
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=18,
            spaceAfter=30,
            alignment=1  # Center
        )
        story.append(Paragraph("TEST FAKTURA", title_style))
        story.append(Spacer(1, 20))
        
        # Test tabulka
        test_data = [
            ['Polozka', 'Castka'],
            ['Elektrina VT', '1000.00 Kc'],
            ['Elektrina NT', '500.00 Kc'],
            ['Distribuce', '200.00 Kc'],
            ['CELKEM', '1700.00 Kc']
        ]
        
        table = Table(test_data)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        story.append(table)
        
        # Vytvoř PDF
        doc.build(story)
        pdf_data = buffer.getvalue()
        buffer.close()
        
        print(f"[OK] ReportLab test uspesny, velikost PDF: {len(pdf_data)} bytu")
        
        # Uloz test PDF
        with open('test_reportlab.pdf', 'wb') as f:
            f.write(pdf_data)
        print("[OK] Test PDF ulozeno jako 'test_reportlab.pdf'")
        
        return True
        
    except Exception as e:
        print(f"[ERROR] Test ReportLab fallback selhal: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    test_reportlab_fallback()