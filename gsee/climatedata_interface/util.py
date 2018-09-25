import os
import urllib.request


PDFS_URL = 'https://agitated-khorana-6ac3a1.netlify.com/'
PDFS_PATH = os.path.join(os.path.dirname(__file__), 'pdf_files')
PDF_FILENAME = 'MERRA2_rad3x3_2011-2015-PDFs_land_prox.nc'


def return_pdf_path():
    pdf_path = os.path.join(PDFS_PATH, PDF_FILENAME)
    if not os.path.exists(pdf_path):
        pdf_url = PDFS_URL + PDF_FILENAME
        retrieve_resource(pdf_url, pdf_path)
    return pdf_path


def retrieve_resource(url, out_path):
    pathname, filename = os.path.split(out_path)
    print('File not yet downloaded, retrieving: {}'.format(filename))
    os.makedirs(pathname, exist_ok=True)
    urllib.request.urlretrieve(url, out_path)
