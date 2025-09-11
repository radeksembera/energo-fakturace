# Jednoduchá náhrada pre prílohu 2 route

@print_bp.route("/<int:stredisko_id>/<int:rok>-<int:mesic>/priloha2/pdf")
def vygenerovat_priloha2_pdf(stredisko_id, rok, mesic):
    """DOČASNÁ JEDNODUCHÁ VERZE - Generuje PDF přílohu 2"""
    if not session.get("user_id"):
        return redirect("/login")

    stredisko = Stredisko.query.get_or_404(stredisko_id)
    if stredisko.user_id != session["user_id"]:
        return "Nepovolený přístup", 403

    try:
        print(f"[DEBUG] Zacinam jednoduchu prilohu 2 PDF pre stredisko {stredisko_id}, obdobie {rok}/{mesic}")
        
        # Vytvoř jednoduchý PDF pomocí ReportLab
        from reportlab.platypus import SimpleDocTemplate, Paragraph
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.pagesizes import A4
        import io
        
        # Vytvoř PDF buffer
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        
        # Vytvoř story
        story = []
        styles = getSampleStyleSheet()
        
        story.append(Paragraph(f"PŘÍLOHA 2 - {stredisko.nazev}", styles['Title']))
        story.append(Paragraph(f"Období: {rok}/{mesic:02d}", styles['Heading2']))
        story.append(Paragraph("Rozpis položek za odběrná místa", styles['Normal']))
        story.append(Paragraph("(Zjednodušená verze pro debugging)", styles['Normal']))
        
        # Vygeneruj PDF
        doc.build(story)
        pdf_data = buffer.getvalue()
        buffer.close()
        
        print(f"[DEBUG] Jednoducha priloha 2 PDF vytvorena, velkost: {len(pdf_data)} bytov")
        
        response = make_response(pdf_data)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'inline; filename=priloha2_{rok}_{mesic:02d}.pdf'
        
        return response

    except Exception as e:
        print(f"[ERROR] Chyba v jednoduche prilohe 2: {e}")
        import traceback
        traceback.print_exc()
        error_msg = str(e)
        flash(f"[ERROR] Chyba při generování PDF: {error_msg}")
        return redirect(url_for('fakturace.fakturace', stredisko_id=stredisko_id))