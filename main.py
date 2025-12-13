#!/usr/bin/env python3
"""
FastAPI app that accepts a PDF upload and returns a version where black/near-black pixels
are replaced with a dark blue color on every page.

Requires:
- poppler (system dependency) for pdf2image rendering
- Python packages listed in requirements.txt

Run:
  pip install -r requirements.txt
  # ensure poppler is installed and in PATH (or set POPPLER_PATH env var)
  uvicorn main:app --reload --port 8000
"""
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse
from typing import List
from io import BytesIO
from pdf2image import convert_from_bytes
from PIL import Image
import numpy as np
import cv2

app = FastAPI(title="PDF Black-to-DarkBlue Converter")

def hex_to_rgb(hexcol: str):
    h = hexcol.lstrip('#')
    if len(h) != 6:
        raise ValueError("hex color must be 6 digits, e.g. #0B3D91")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

def replace_black_with_color(pil_img: Image.Image, threshold: int = 60, hex_color: str = "#0B3D91") -> Image.Image:
    """
    Replace black/near-black pixels in a PIL.Image with the provided color.
    Uses a smooth blend based on pixel darkness to preserve anti-aliased edges.
    """
    if pil_img.mode != "RGB":
        img = pil_img.convert("RGBA")
    else:
        img = pil_img.convert("RGB")

    arr = np.asarray(img)  # shape HxWx3 or HxWx4
    has_alpha = (arr.shape[2] == 4)

    if has_alpha:
        bgr = arr[:, :, :3].astype(np.float32)
        alpha = arr[:, :, 3].astype(np.float32) / 255.0
    else:
        bgr = arr[:, :, :3].astype(np.float32)
        alpha = None

    # Convert to RGB order for color math (arr is in RGB because PIL -> numpy gives RGB)
    rgb = bgr  # currently RGB

    # Compute darkness measure: use max channel (works well for black-like pixels)
    max_channel = np.max(rgb, axis=2)  # 0..255

    thresh = float(max(0, min(255, threshold)))
    # Blend factor: 1 at black (max_channel==0), 0 at >= threshold
    factor = (thresh - max_channel) / thresh if thresh > 0 else (max_channel == 0).astype(np.float32)
    factor = np.clip(factor, 0.0, 1.0)
    factor3 = np.repeat(factor[:, :, np.newaxis], 3, axis=2)

    tgt_rgb = np.array(hex_to_rgb(hex_color), dtype=np.float32)

    out_rgb = (1.0 - factor3) * rgb + factor3 * tgt_rgb
    out_rgb = np.clip(out_rgb, 0, 255).astype(np.uint8)

    if has_alpha:
        out_arr = np.dstack((out_rgb, (alpha * 255).astype(np.uint8)))
        out_img = Image.fromarray(out_arr, mode="RGBA")
        out_img = out_img.convert("RGB")  # PDFs generally better saved as RGB
    else:
        out_img = Image.fromarray(out_rgb, mode="RGB")

    return out_img

@app.post("/convert", summary="Convert uploaded PDF, replace black with dark blue")
async def convert_pdf(
    file: UploadFile = File(..., description="PDF file to process"),
    threshold: int = Form(60, description="Darkness threshold (0-255)"),
    hex_color: str = Form("#0B3D91", description="Replacement hex color, e.g. #0B3D91")
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Uploaded file must be a PDF")

    pdf_bytes = await file.read()
    try:
        # Render PDF pages to images (high DPI for quality)
        pages = convert_from_bytes(pdf_bytes, dpi=300)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to render PDF pages: {e}")

    processed_pages: List[Image.Image] = []
    for img in pages:
        processed = replace_black_with_color(img, threshold=threshold, hex_color=hex_color)
        processed_pages.append(processed)

    out_io = BytesIO()
    try:
        if len(processed_pages) == 1:
            processed_pages[0].save(out_io, format="PDF", resolution=300)
        else:
            first, rest = processed_pages[0], processed_pages[1:]
            first.save(out_io, format="PDF", save_all=True, append_images=rest, resolution=300)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create output PDF: {e}")

    out_io.seek(0)
    headers = {
        "Content-Disposition": f'attachment; filename="converted_{file.filename}"'
    }
    return StreamingResponse(out_io, media_type="application/pdf", headers=headers)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)