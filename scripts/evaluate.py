from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch
from torch.utils.data import DataLoader
from tqdm import tqdm

from tianshan_sentinel.dataset import ChangeDetectionDataset
from tianshan_sentinel.metrics import BinarySegmentationMetrics
from tianshan_sentinel.model import load_model_from_checkpoint


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--split", default="test")
    parser.add_argument("--image-size", type=int, default=256)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--output", default="artifacts/metrics.json")
    args = parser.parse_args()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model, metadata = load_model_from_checkpoint(args.checkpoint, device)
    dataset = ChangeDetectionDataset(args.data_root, args.split, args.image_size)
    loader = DataLoader(dataset, batch_size=args.batch_size, num_workers=2)
    metrics = BinarySegmentationMetrics(metadata["threshold"])
    temperature = metadata["temperature"]
    with torch.no_grad():
        for batch in tqdm(loader):
            logits = model(batch["before"].to(device), batch["after"].to(device)) / temperature
            metrics.update(logits.cpu(), batch["mask"])
    result = {
        "dataset": "LEVIR-CD",
        "split": args.split,
        "samples": len(dataset),
        "threshold": metadata["threshold"],
        "temperature": temperature,
        **metrics.compute(),
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

