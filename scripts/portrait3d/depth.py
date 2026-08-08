"""
depth.py — estimate a depth map from a single portrait, fully on-device.

The faithful half of the portrait-3D pipeline: a monocular depth model
(Depth-Anything V2, small) looks at one photo and estimates how far each pixel
is from the camera. No geometry is invented — the person's own pixels drive a
real relief that Blender later displaces and textures. Runs on Apple MPS if
available, else CPU. First run downloads the model weights once; nothing leaves
the machine after that.

Output: a 16-bit grayscale PNG where brighter = nearer (the convention Blender's
displacement expects), plus a normalized copy for eyeballing.

  python depth.py input/mom.png work/mom_depth.png
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from transformers import pipeline

MODEL = "depth-anything/Depth-Anything-V2-Small-hf"


def _device() -> str:
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def estimate(src: Path, out: Path) -> Path:
    dev = _device()
    print(f"[depth] device={dev} model={MODEL}")
    img = Image.open(src).convert("RGB")
    print(f"[depth] input {img.size[0]}x{img.size[1]}")

    pipe = pipeline("depth-estimation", model=MODEL, device=dev)
    result = pipe(img)
    depth = np.asarray(result["depth"], dtype=np.float32)

    # normalize 0..1, brighter = nearer (Depth-Anything gives larger=nearer already)
    d = depth - depth.min()
    if d.max() > 0:
        d /= d.max()

    out.parent.mkdir(parents=True, exist_ok=True)
    # 16-bit for smooth displacement, no banding
    Image.fromarray((d * 65535).astype(np.uint16), mode="I;16").save(out)
    # 8-bit preview to glance at
    preview = out.with_name(out.stem + "_preview.png")
    Image.fromarray((d * 255).astype(np.uint8), mode="L").save(preview)
    print(f"[depth] wrote {out} (+ {preview.name})")
    return out


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: python depth.py <input_image> <output_depth.png>")
        raise SystemExit(2)
    estimate(Path(sys.argv[1]), Path(sys.argv[2]))
