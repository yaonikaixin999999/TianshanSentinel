from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch

from tianshan_sentinel.model import load_model_from_checkpoint


class CalibratedModel(torch.nn.Module):
    def __init__(self, model, temperature: float):
        super().__init__()
        self.model = model
        self.temperature = temperature

    def forward(self, before, after):
        return self.model(before, after) / self.temperature


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--output", default="artifacts/model.onnx")
    parser.add_argument("--image-size", type=int, default=256)
    args = parser.parse_args()
    model, metadata = load_model_from_checkpoint(args.checkpoint, "cpu")
    wrapped = CalibratedModel(model, metadata["temperature"]).eval()
    sample = torch.randn(1, 3, args.image_size, args.image_size)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    torch.onnx.export(
        wrapped,
        (sample, sample),
        str(output),
        input_names=["before", "after"],
        output_names=["logits"],
        dynamic_axes={"before": {0: "batch"}, "after": {0: "batch"}, "logits": {0: "batch"}},
        opset_version=17,
    )
    sidecar = output.with_suffix(".metadata.json")
    sidecar.write_text(
        json.dumps(
            {
                "format": "TianshanSentinel ONNX metadata",
                "image_size": args.image_size,
                "threshold": metadata["threshold"],
                "temperature_embedded": metadata["temperature"],
                "checkpoint_epoch": metadata["epoch"],
                "checkpoint_metrics": metadata["metrics"],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"saved={output}; metadata={sidecar}")


if __name__ == "__main__":
    main()
