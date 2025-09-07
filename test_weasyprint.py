from weasyprint import HTML
import traceback

try:
    html = HTML(string='<html><body>test</body></html>')
    pdf = html.write_pdf()
    print('WeasyPrint OK')
    print(f'PDF size: {len(pdf)} bytes')
except Exception as e:
    print(f'WeasyPrint chyba: {e}')
    traceback.print_exc()