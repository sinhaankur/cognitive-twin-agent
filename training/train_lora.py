"""
LoRA fine-tune Vera's voice & conversation — on this Mac, with MLX.

This is the real "deep training": a Low-Rank Adaptation of a small Qwen2.5 model
on training/data/*.jsonl (built by build_dataset.py). It runs on Apple Silicon via
MLX — no cloud, no GPU rental. The result is an adapter that makes the model talk
more like Vera: warm, concise, in-character, holding space.

Pipeline:
  1. python -m training.build_dataset          # make the data
  2. python -m training.train_lora             # fine-tune (this file)
  3. python -m training.train_lora --fuse      # bake the adapter into a model
  4. (optional) import into Ollama as `vera-tuned` — see --fuse output
  5. python -m evals.conversation_eval --model <the tuned model>   # measure the lift

MLX trains from a HuggingFace model id (downloaded + cached once). Defaults to a
small instruct model so it fits comfortably on a 32 GB Mac. Everything is thin
wrappers over `mlx_lm` so the heavy lifting stays in a maintained library.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_DATA = _HERE / "data"
_ADAPTERS = _HERE / "adapters"

# Small enough to train on a 32 GB M-series Mac; same family as empathia (qwen2.5).
DEFAULT_MODEL = "Qwen/Qwen2.5-3B-Instruct"


def _run(cmd: list[str]) -> int:
    print("+ " + " ".join(cmd))
    return subprocess.call(cmd)


def train(model: str, iters: int, batch: int, lr: float) -> int:
    if not (_DATA / "train.jsonl").is_file():
        print("No training data — run: python -m training.build_dataset", file=sys.stderr)
        return 1
    _ADAPTERS.mkdir(parents=True, exist_ok=True)
    # mlx_lm.lora reads train.jsonl / valid.jsonl from --data (a directory).
    return _run([
        sys.executable, "-m", "mlx_lm", "lora",
        "--model", model,
        "--train",
        "--data", str(_DATA),
        "--adapter-path", str(_ADAPTERS),
        "--iters", str(iters),
        "--batch-size", str(batch),
        "--learning-rate", str(lr),
        "--num-layers", "8",          # LoRA on the top 8 layers — light + fast
    ])


def fuse(model: str) -> int:
    """Bake the trained adapter into a standalone model dir, and print how to
    import it into Ollama so the app can use it."""
    if not (_ADAPTERS / "adapters.safetensors").is_file():
        print("No adapter yet — train first: python -m training.train_lora", file=sys.stderr)
        return 1
    fused = _HERE / "vera-tuned"
    rc = _run([
        sys.executable, "-m", "mlx_lm", "fuse",
        "--model", model,
        "--adapter-path", str(_ADAPTERS),
        "--save-path", str(fused),
    ])
    if rc == 0:
        print("\nFused model written to:", fused)
        print("To use it in Vera via Ollama, create a Modelfile:")
        print(f'  FROM {fused}')
        print("  then: ollama create vera-tuned -f Modelfile")
        print("  then run the eval: python -m evals.conversation_eval --model vera-tuned")
    return rc


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="LoRA fine-tune Vera's conversation")
    ap.add_argument("--model", default=DEFAULT_MODEL, help="base HF model id")
    ap.add_argument("--iters", type=int, default=300, help="training iterations")
    ap.add_argument("--batch", type=int, default=2, help="batch size (keep small on a Mac)")
    ap.add_argument("--lr", type=float, default=1e-4, help="learning rate")
    ap.add_argument("--fuse", action="store_true", help="bake the trained adapter into a model")
    args = ap.parse_args(argv)
    if args.fuse:
        return fuse(args.model)
    return train(args.model, args.iters, args.batch, args.lr)


if __name__ == "__main__":
    raise SystemExit(main())
