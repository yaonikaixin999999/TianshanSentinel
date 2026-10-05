from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch
from torch.utils.data import DataLoader
from tqdm import tqdm

from tianshan_sentinel.dataset import ChangeDetectionDataset
from tianshan_sentinel.model import load_model_from_checkpoint


def main() -> None:
    parser = argparse.ArgumentParser(description="Select a probability threshold on the validation split")
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--output", default=None)
    parser.add_argument("--metrics-output", default=None)
    parser.add_argument("--image-size", type=int, default=256)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--minimum", type=float, default=0.20)
    parser.add_argument("--maximum", type=float, default=0.80)
    parser.add_argument("--steps", type=int, default=61)
    args = parser.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model, metadata = load_model_from_checkpoint(args.checkpoint, device)
    dataset = ChangeDetectionDataset(args.data_root, "val", args.image_size)
    loader = DataLoader(dataset, batch_size=args.batch_size, num_workers=2, pin_memory=device.type == "cuda")
    thresholds = torch.linspace(args.minimum, args.maximum, args.steps, device=device)
    true_positive = torch.zeros(args.steps, dtype=torch.int64, device=device)
    false_positive = torch.zeros_like(true_positive)
    false_negative = torch.zeros_like(true_positive)

    with torch.no_grad():
        for batch in tqdm(loader, desc="threshold sweep"):
            logits = model(
                batch["before"].to(device, non_blocking=True),
                batch["after"].to(device, non_blocking=True),
            ) / metadata["temperature"]
            probabilities = torch.sigmoid(logits)
            truth = batch["mask"].to(device, non_blocking=True) >= 0.5
            predictions = probabilities.unsqueeze(0) >= thresholds[:, None, None, None, None]
            truth = truth.unsqueeze(0)
            true_positive += (predictions & truth).sum(dim=(1, 2, 3, 4))
            false_positive += (predictions & ~truth).sum(dim=(1, 2, 3, 4))
            false_negative += (~predictions & truth).sum(dim=(1, 2, 3, 4))

    epsilon = 1e-8
    iou = true_positive / (true_positive + false_positive + false_negative + epsilon)
    best_index = int(torch.argmax(iou))
    selected_threshold = float(thresholds[best_index])
    result = {
        "split": "val",
        "samples": len(dataset),
        "temperature": metadata["temperature"],
        "minimum": args.minimum,
        "maximum": args.maximum,
        "steps": args.steps,
        "selected_threshold": selected_threshold,
        "selected_iou": float(iou[best_index]),
    }

    checkpoint = torch.load(args.checkpoint, map_location="cpu", weights_only=False)
    checkpoint["threshold"] = selected_threshold
    checkpoint["threshold_selection"] = result
    source = Path(args.checkpoint)
    output = Path(args.output or source.with_name(f"{source.stem}_thresholded.pt"))
    output.parent.mkdir(parents=True, exist_ok=True)
    torch.save(checkpoint, output)
    metrics_output = Path(args.metrics_output or output.with_name("threshold_selection.json"))
    metrics_output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"saved={output}; metrics={metrics_output}")


if __name__ == "__main__":
    main()
