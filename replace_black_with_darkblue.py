#!/usr/bin/env python3
"""
Replace black/near-black pixels with a dark blue, preserving anti-aliased edges.

Usage:
  python replace_black_with_darkblue.py input.png output.png [--threshold 60] [--hex #0B3D91]

Default threshold is 60 (0-255). Increase to capture lighter grays; decrease for only very dark pixels.
"""
import sys
import os
import argparse
import numpy as np
import cv2

def hex_to_rgb(hexcol):
    h = hexcol.lstrip('#')
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

def main():
    p = argparse.ArgumentParser(description="Replace black/near-black pixels with a dark blue (smooth blend).")
    p.add_argument('input', help='input image path')
    p.add_argument('output', help='output image path')
    p.add_argument('--threshold', type=int, default=60, help='distance threshold from black (0-255). Default 60')
    p.add_argument('--hex', default='#0B3D91', help='replacement hex color (default #0B3D91)')
    args = p.parse_args()

    if not os.path.isfile(args.input):
        print("Input file not found:", args.input)
        sys.exit(2)

    tgt_rgb = np.array(hex_to_rgb(args.hex), dtype=np.uint8)  # RGB
    # Read with cv2 (BGR)
    src_bgr = cv2.imread(args.input, cv2.IMREAD_UNCHANGED)
    if src_bgr is None:
        print("Could not read input image.")
        sys.exit(1)

    # Handle alpha if present
    if src_bgr.shape[2] == 4:
        bgr = src_bgr[:, :, :3].astype(np.float32)
        alpha = src_bgr[:, :, 3].astype(np.float32) / 255.0
    else:
        bgr = src_bgr[:, :, :3].astype(np.float32)
        alpha = None

    # Convert to RGB order for color math
    rgb = bgr[:, :, ::-1]  # BGR->RGB

    # Compute darkness measure: use max channel (works well for black-like pixels)
    max_channel = np.max(rgb, axis=2)  # 0..255
    thresh = float(args.threshold)

    # Create blend factor 0..1: 1 at pure black (max_channel==0), 0 at >= threshold
    factor = (thresh - max_channel) / thresh
    factor = np.clip(factor, 0.0, 1.0)  # shape HxW

    # Expand factor to 3 channels
    factor3 = np.repeat(factor[:, :, np.newaxis], 3, axis=2)

    # Replacement color as float RGB
    tgt = np.array(tgt_rgb, dtype=np.float32)

    # New RGB = (1-factor)*orig + factor*tgt
    out_rgb = (1.0 - factor3) * rgb + factor3 * tgt

    # Convert back to BGR uint8
    out_bgr = np.clip(out_rgb[:, :, ::-1], 0, 255).astype(np.uint8)

    if alpha is not None:
        out = np.dstack((out_bgr, (alpha * 255).astype(np.uint8)))
    else:
        out = out_bgr

    ok = cv2.imwrite(args.output, out)
    if not ok:
        print("Failed to write output.")
        sys.exit(1)
    print("Wrote", args.output)

if __name__ == '__main__':
    main()