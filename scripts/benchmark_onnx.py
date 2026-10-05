from __future__ import annotations

import argparse
import json
import platform
import time
from pathlib import Path

import numpy as np
import onnxruntime as ort


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark one ONNX forward pass on CPU")
    parser.add_argument("--model", default="artifacts/model.onnx")
    parser.add_argument("--image-size", type=int, default=256)
    parser.add_argument("--warmup", type=int, default=10)
    parser.add_argument("--iterations", type=int, default=100)
    parser.add_argument("--output", default="artifacts/onnx_cpu_benchmark.json")
    args = parser.parse_args()

    model_path = Path(args.model)
    options = ort.SessionOptions()
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    session = ort.InferenceSession(str(model_path), sess_options=options, providers=["CPUExecutionProvider"])
    rng = np.random.default_rng(2026)
    before = rng.standard_normal((1, 3, args.image_size, args.image_size), dtype=np.float32)
    after = rng.standard_normal((1, 3, args.image_size, args.image_size), dtype=np.float32)

    for _ in range(args.warmup):
        session.run(None, {"before": before, "after": after})

    durations_ms: list[float] = []
    for _ in range(args.iterations):
        started = time.perf_counter()
        session.run(None, {"before": before, "after": after})
        durations_ms.append((time.perf_counter() - started) * 1000)

    timings = np.asarray(durations_ms)
    result = {
        "runtime": "onnxruntime",
        "provider": session.get_providers()[0],
        "onnxruntime_version": ort.__version__,
        "platform": platform.platform(),
        "processor": platform.processor(),
        "image_size": args.image_size,
        "batch_size": 1,
        "warmup": args.warmup,
        "iterations": args.iterations,
        "mean_ms": float(timings.mean()),
        "p50_ms": float(np.percentile(timings, 50)),
        "p95_ms": float(np.percentile(timings, 95)),
        "minimum_ms": float(timings.min()),
        "maximum_ms": float(timings.max()),
        "model_size_mb": model_path.stat().st_size / (1024**2),
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
