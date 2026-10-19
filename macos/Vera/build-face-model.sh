#!/usr/bin/env bash
# Build "FaceEmbedder.mlmodel" — a REAL face-recognition embedding model for Vera.
#
# Why this exists: Apple's Vision ships face DETECTION / landmarks / quality, but
# NO public face-RECOGNITION (identity) model. VNGenerateImageFeaturePrint is a
# general whole-image embedding — fine for "you vs a stranger", not family-grade.
# Genuine recognition (the way FaceNet/ArcFace — and the brain's fusiform face
# area — do it) needs a face-TRAINED embedding model. This converts an open
# ArcFace model (InsightFace) to Core ML so it runs on the Neural Engine,
# on-device, nothing uploaded.
#
# Output: FaceEmbedder.mlpackage (and compiled .mlmodelc) in this folder, which
# build-app.sh copies into Vera.app/Contents/Resources. FaceID.swift uses it when
# present and falls back to the general embedding when it isn't — so the app never
# breaks if you skip this step.
#
# This needs a Python coremltools supports (3.10–3.12 as of writing), NOT 3.14.
# Run it once; the model is static.
#
#   ./build-face-model.sh
#
set -euo pipefail
cd "$(dirname "$0")"

PYBIN="${PYBIN:-python3.11}"
if ! command -v "$PYBIN" >/dev/null 2>&1; then
  echo "Need a coremltools-compatible Python (3.10–3.12). Install one, e.g.:"
  echo "    brew install python@3.11"
  echo "then re-run:  PYBIN=python3.11 ./build-face-model.sh"
  exit 1
fi

VENV=".facemodel-venv"
if [ ! -d "$VENV" ]; then
  echo "[1/4] Creating build venv ($PYBIN) ..."
  "$PYBIN" -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"

echo "[2/4] Installing conversion tooling (insightface, onnx→torch, coremltools) ..."
pip install --quiet --upgrade pip
# Modern coremltools has NO direct ONNX path, so we go ONNX → PyTorch (onnx2torch)
# → traced → Core ML. torch + onnx2torch do the bridge.
pip install --quiet "coremltools>=8.0" "onnx>=1.16" "insightface>=0.7" onnxruntime \
    "numpy<2" torch onnx2torch

echo "[3/4] Fetching ArcFace weights + converting to Core ML ..."
python3 - <<'PY'
import os, sys
import numpy as np

# InsightFace ships ArcFace (buffalo_l → w600k_r50) as ONNX; download via its model zoo.
from insightface.utils import storage
name = "buffalo_l"
storage.ensure_available("models", name, root=os.path.expanduser("~/.insightface"))
model_dir = os.path.expanduser(f"~/.insightface/models/{name}")
rec = None
for f in os.listdir(model_dir):
    if f.endswith(".onnx") and ("w600k" in f or "glint" in f or "arcface" in f.lower()):
        rec = os.path.join(model_dir, f)
if rec is None:
    sys.exit(f"could not find the ArcFace .onnx inside {model_dir}: {os.listdir(model_dir)}")
print("ArcFace ONNX:", rec)

import torch
from onnx2torch import convert as onnx2torch_convert
import coremltools as ct

# ONNX → PyTorch
torch_model = onnx2torch_convert(rec).eval()

# ArcFace input is a 112x112 face. The ONNX graph takes an already-normalized
# [1,3,112,112] float tensor (InsightFace normalizes (x-127.5)/127.5 → [-1,1]).
# We bake that normalization into the Core ML image input via scale + bias so the
# app can hand it a plain image: pixel/127.5 - 1  →  scale=1/127.5, bias=-1.
example = torch.rand(1, 3, 112, 112)
traced = torch.jit.trace(torch_model, example)

scale = 1.0 / 127.5
mlmodel = ct.convert(
    traced,
    inputs=[ct.ImageType(name="input", shape=(1, 3, 112, 112),
                         scale=scale, bias=[-1.0, -1.0, -1.0],
                         color_layout=ct.colorlayout.RGB)],
    minimum_deployment_target=ct.target.macOS13,
    compute_units=ct.ComputeUnit.ALL,
)
mlmodel.short_description = "ArcFace face-identity embedding (InsightFace buffalo_l, r50). On-device, 512-D."
out = os.path.join(os.getcwd(), "FaceEmbedder.mlpackage")
mlmodel.save(out)
print("saved:", out)
PY

echo "[4/4] Compiling to .mlmodelc for the bundle ..."
xcrun coremlcompiler compile FaceEmbedder.mlpackage . || \
  echo "  (coremlcompiler step skipped — build-app.sh will compile at bundle time)"

echo
echo "Done. FaceEmbedder.mlpackage is ready."
echo "Rebuild the app:  ./build-app.sh   (it copies the model into Resources)"
