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


def replace_color_with_black(pil_img: Image.Image, hex_color: str = "#0B3D91", tolerance: int = 60) -> Image.Image:
    """
    Replace pixels near `hex_color` with black. `tolerance` is Euclidean distance
    in RGB space (0-441). Uses a smooth blend so anti-aliased edges are preserved.
    """
    if pil_img.mode != "RGB":
        img = pil_img.convert("RGBA")
    else:
        img = pil_img.convert("RGB")

    arr = np.asarray(img)  # HxWx3 or HxWx4
    has_alpha = (arr.shape[2] == 4)

    if has_alpha:
        rgb = arr[:, :, :3].astype(np.float32)
        alpha = arr[:, :, 3].astype(np.float32) / 255.0
    else:
        rgb = arr[:, :, :3].astype(np.float32)
        alpha = None

    tgt = np.array(hex_to_rgb(hex_color), dtype=np.float32)
    # Euclidean distance
    diff = rgb - tgt[np.newaxis, np.newaxis, :]
    dist = np.linalg.norm(diff, axis=2)

    tol = float(max(0.0, tolerance))
    if tol == 0:
        mask = (dist == 0).astype(np.float32)
        factor = np.repeat(mask[:, :, np.newaxis], 3, axis=2)
    else:
        factor = (tol - dist) / tol
        factor = np.clip(factor, 0.0, 1.0)
        factor = np.repeat(factor[:, :, np.newaxis], 3, axis=2)

    # Blend towards black (0,0,0)
    out_rgb = (1.0 - factor) * rgb
    out_rgb = np.clip(out_rgb, 0, 255).astype(np.uint8)

    if has_alpha:
        out_arr = np.dstack((out_rgb, (alpha * 255).astype(np.uint8)))
        out_img = Image.fromarray(out_arr, mode="RGBA")
        out_img = out_img.convert("RGB")
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

    # mode: 'replace' = replace black with supplied color (default)
    # mode: 'binarize' = convert page to pure black/white (useful for scanned documents)
    mode = 'replace'
    try:
        # if caller provided a form field 'mode', prefer it
        form = file._form if hasattr(file, '_form') else None
    except Exception:
        form = None

    # FastAPI doesn't expose additional form fields via UploadFile directly here,
    # so accept an optional query param or environment override — fallback to 'replace'.
    # If you want to pass mode via form, send it as a separate form field named 'mode'.
    from fastapi import Request
    try:
        # Try reading Request from context if available
        import inspect
        for frame in inspect.stack():
            loc = frame.frame.f_locals
            if 'request' in loc and isinstance(loc['request'], Request):
                req = loc['request']
                q = req.query_params.get('mode')
                if q:
                    mode = q
                break
    except Exception:
        pass

    # Simple approach: check environment var as alternate control
    import os
    mode = os.environ.get('PDF_CONVERT_MODE', mode)

    processed_pages: List[Image.Image] = []

    def binarize_image(pil_img: Image.Image) -> Image.Image:
        gray = pil_img.convert('L')
        arr = np.asarray(gray)
        # Otsu thresholding
        try:
            _, th = cv2.threshold(arr, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        except Exception:
            # fallback to simple threshold
            _, th = cv2.threshold(arr, int(threshold), 255, cv2.THRESH_BINARY)
        rgb = np.stack([th, th, th], axis=2).astype(np.uint8)
        return Image.fromarray(rgb, mode='RGB')

    for img in pages:
        if mode == 'binarize':
            processed = binarize_image(img)
        else:
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


@app.post("/revert", summary="Revert replacement color back to black")
async def revert_pdf(
    file: UploadFile = File(..., description="PDF file to process"),
    hex_color: str = Form("#0B3D91", description="Replacement hex color to detect, e.g. #0B3D91"),
    tolerance: int = Form(60, description="Color tolerance (0-441) to match replacement color")
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Uploaded file must be a PDF")

    pdf_bytes = await file.read()
    try:
        # Render PDF pages to images
        pages = convert_from_bytes(pdf_bytes, dpi=300)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to render PDF pages: {e}")

    processed_pages: List[Image.Image] = []
    for img in pages:
        processed = replace_color_with_black(img, hex_color=hex_color, tolerance=tolerance)
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
        "Content-Disposition": f'attachment; filename="reverted_{file.filename}"'
    }
    return StreamingResponse(out_io, media_type="application/pdf", headers=headers)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)