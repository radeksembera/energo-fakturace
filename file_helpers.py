"""
file_helpers.py
Pomocné funkce pro práci se soubory faktur
"""

from pathlib import Path

def get_faktury_path(stredisko_id, rok, mesic):
    """Vrátí cestu ke složce pro faktury daného období"""
    base_path = Path("static/faktury")
    folder_path = base_path / str(stredisko_id) / f"{rok}-{mesic:02d}"
    
    # Vytvoř složku pokud neexistuje
    folder_path.mkdir(parents=True, exist_ok=True)
    
    return folder_path

def get_faktura_filenames(stredisko_id, rok, mesic):
    """Vrátí názvy souborů pro všechny typy faktur"""
    return {
        'faktura_html': f"faktura_{rok}_{mesic:02d}.html",
        'faktura_pdf': f"faktura_{rok}_{mesic:02d}.pdf", 
        'zalohova_html': f"zalohova_{rok}_{mesic:02d}.html",
        'zalohova_pdf': f"zalohova_{rok}_{mesic:02d}.pdf",
        'priloha1_html': f"priloha1_{rok}_{mesic:02d}.html",
        'priloha1_pdf': f"priloha1_{rok}_{mesic:02d}.pdf",
        'priloha2_html': f"priloha2_{rok}_{mesic:02d}.html",
        'priloha2_pdf': f"priloha2_{rok}_{mesic:02d}.pdf"
    }

def check_faktury_exist(stredisko_id, rok, mesic):
    """Zkontroluje které faktury jsou vygenerovány"""
    folder_path = get_faktury_path(stredisko_id, rok, mesic)
    filenames = get_faktura_filenames(stredisko_id, rok, mesic)
    
    status = {}
    for file_type, filename in filenames.items():
        file_path = folder_path / filename
        status[file_type] = file_path.exists()
    
    return status