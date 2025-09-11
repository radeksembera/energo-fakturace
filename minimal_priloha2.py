# Minimální náhrada pro přílohu 2 - pouze pro testování

@print_bp.route("/<int:stredisko_id>/<int:rok>-<int:mesic>/priloha2/pdf")
def vygenerovat_priloha2_pdf(stredisko_id, rok, mesic):
    """MINIMÁLNÍ TEST VERZE - pouze text"""
    if not session.get("user_id"):
        return redirect("/login")

    stredisko = Stredisko.query.get_or_404(stredisko_id)
    if stredisko.user_id != session["user_id"]:
        return "Nepovolený přístup", 403

    # Jednoduše vrátíme text místo PDF
    return f"""
    <html>
    <head><title>Test Příloha 2</title></head>
    <body>
        <h1>TEST PŘÍLOHA 2</h1>
        <p>Středisko ID: {stredisko_id}</p>
        <p>Období: {rok}/{mesic:02d}</p>
        <p>Středisko: {stredisko.nazev}</p>
        <p>Pokud vidíte tuto stránku, route funguje správně.</p>
    </body>
    </html>
    """