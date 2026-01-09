# PDF Black-to-DarkBlue Converter

Small FastAPI service that accepts a PDF upload and returns a new PDF where black or
near-black pixels are replaced with a dark blue color. It renders pages to images,
recolors dark pixels with a smooth blend to preserve anti-aliased edges, then
reassembles the pages into a PDF.

## Requirements

- Python 3.8+
- poppler (system dependency) — required by `pdf2image` to render PDF pages
- Python packages listed in `requirements.txt` (see repo root)

On Windows, install Poppler (e.g., from: http://blog.alivate.com.au/poppler-windows/)
and either add the `bin` folder to `PATH` or set `POPPLER_PATH` to the folder containing
Poppler's `bin` executable files.

Example (PowerShell, current session):

```powershell
#$env:POPPLER_PATH = 'C:\path\to\poppler\Library\bin'
```

## Install

Create and activate a virtual environment, then install Python deps:

```bash
# Windows (PowerShell)
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

If you don't have a `requirements.txt`, the main dependencies are:

```
fastapi
uvicorn
pdf2image
Pillow
numpy
opencv-python
```

## Run the app

Two ways to run:

```bash
# Recommended (uvicorn)
uvicorn main:app --reload --port 8000

# Or run the script directly (calls uvicorn)
python main.py
```

The server listens on port 8000 by default. Open `http://localhost:8000/docs`
to view the interactive API (Swagger UI).

## API: POST /convert

Accepts a `multipart/form-data` request with the following fields:

- `file` (file) — PDF to convert
- `threshold` (int, form) — darkness threshold (0-255); default 60
- `hex_color` (str, form) — replacement color in hex (e.g. `#0B3D91`)

Response: `application/pdf` attachment containing the converted PDF.

### Example curl

```bash
curl -X POST "http://localhost:8000/convert" \
>  -F "file=@input.pdf" \
>  -F "threshold=60" \
>  -F "hex_color=#0B3D91" --output converted.pdf
```

### Example Python client

```python
import requests

url = 'http://localhost:8000/convert'
with open('input.pdf','rb') as f:
    files = {'file': ('input.pdf', f, 'application/pdf')}
    data = {'threshold': '60', 'hex_color': '#0B3D91'}
    r = requests.post(url, files=files, data=data)
    with open('converted.pdf', 'wb') as out:
        out.write(r.content)
```

## Notes & troubleshooting

- Ensure Poppler is installed and reachable by the process; missing Poppler causes
  `pdf2image.convert_from_bytes` to fail.
- Large PDFs or high DPI (300) can use substantial memory—adjust `dpi` in
  `convert_from_bytes` or process pages in smaller batches if needed.
- The app expects color PDFs/raster content; vector-only PDFs may rasterize.

## Files

- `main.py`: FastAPI application and entrypoint

---
Created to document how to install and run the converter and how to call `/convert`.
