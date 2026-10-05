from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort
import torch

from tianshan_sentinel.model import load_model_from_checkpoint


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Check ONNX structure and compare it with the PyTorch checkpoint")
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--model", default="artifacts/model.onnx")
    parser.add_argument("--image-size", type=int, default=256)
    parser.add_argument("--output", default="artifacts/onnx_verification.json")
    parser.add_argument("--atol", type=float, default=1e-4)
    parser.add_argument("--rtol", type=float, default=1e-4)
    args = parser.parse_args()

    model_path = Path(args.model)
    onnx.checker.check_model(onnx.load(model_path))
    torch_model, metadata = load_model_from_checkpoint(args.checkpoint, "cpu")
    rng = np.random.default_rng(2026)
    before = rng.standard_normal((1, 3, args.image_size, args.image_size), dtype=np.float32)
    after = rng.standard_normal((1, 3, args.image_size, args.image_size), dtype=np.float32)
    with torch.no_grad():
        torch_output = (
            torch_model(torch.from_numpy(before), torch.from_numpy(after)) / metadata["temperature"]
        ).numpy()
    session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
    onnx_output = session.run(None, {"before": before, "after": after})[0]
    difference = np.abs(torch_output - onnx_output)
    equivalent = bool(np.allclose(torch_output, onnx_output, atol=args.atol, rtol=args.rtol))
    result = {
        "onnx_checker_passed": True,
        "pytorch_onnx_equivalent": equivalent,
        "absolute_tolerance": args.atol,
        "relative_tolerance": args.rtol,
        "maximum_absolute_error": float(difference.max()),
        "mean_absolute_error": float(difference.mean()),
        "model_size_bytes": model_path.stat().st_size,
        "model_sha256": _sha256(model_path),
        "threshold": metadata["threshold"],
        "temperature": metadata["temperature"],
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not equivalent:
        raise RuntimeError("ONNX output differs from the PyTorch checkpoint beyond tolerance")


if __name__ == "__main__":
    main()
