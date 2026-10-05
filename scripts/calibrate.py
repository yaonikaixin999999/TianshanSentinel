from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch
from torch.nn import functional as F
from torch.utils.data import DataLoader
from tqdm import tqdm

from tianshan_sentinel.dataset import ChangeDetectionDataset
from tianshan_sentinel.model import load_model_from_checkpoint


def calibration_metrics(logits: torch.Tensor, targets: torch.Tensor, temperature: float) -> dict[str, float]:
    scaled_logits = logits / temperature
    probabilities = torch.sigmoid(scaled_logits)
    nll = F.binary_cross_entropy_with_logits(scaled_logits, targets)
    brier = torch.mean((probabilities - targets) ** 2)
    edges = torch.linspace(0.0, 1.0, 16)
    bins = torch.bucketize(probabilities, edges[1:-1])
    ece = torch.zeros(())
    for index in range(15):
        selected = bins == index
        if selected.any():
            weight = selected.float().mean()
            confidence = probabilities[selected].mean()
            observed = targets[selected].mean()
            ece += weight * (confidence - observed).abs()
    return {"nll": float(nll), "brier": float(brier), "ece_15": float(ece)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Fit scalar temperature on validation logits")
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--output", default=None)
    parser.add_argument("--metrics-output", default=None)
    parser.add_argument("--image-size", type=int, default=256)
    args = parser.parse_args()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model, _ = load_model_from_checkpoint(args.checkpoint, device)
    loader = DataLoader(ChangeDetectionDataset(args.data_root, "val", args.image_size), batch_size=4)
    logits_list, targets_list = [], []
    with torch.no_grad():
        for batch in tqdm(loader):
            logits_list.append(model(batch["before"].to(device), batch["after"].to(device)).cpu())
            targets_list.append(batch["mask"])
    logits = torch.cat(logits_list).flatten()
    targets = torch.cat(targets_list).flatten()
    if logits.numel() > 3_000_000:
        torch.manual_seed(2026)
        indices = torch.randperm(logits.numel())[:3_000_000]
        logits, targets = logits[indices], targets[indices]
    log_temperature = torch.zeros(1, requires_grad=True)
    optimizer = torch.optim.LBFGS([log_temperature], lr=0.05, max_iter=60)

    def closure():
        optimizer.zero_grad()
        loss = F.binary_cross_entropy_with_logits(logits / log_temperature.exp(), targets)
        loss.backward()
        return loss

    optimizer.step(closure)
    temperature = float(log_temperature.exp().detach())
    metrics = {
        "pixels_sampled": logits.numel(),
        "temperature": temperature,
        "before": calibration_metrics(logits, targets, 1.0),
        "after": calibration_metrics(logits, targets, temperature),
    }
    checkpoint = torch.load(args.checkpoint, map_location="cpu", weights_only=False)
    checkpoint["temperature"] = temperature
    checkpoint["calibration"] = metrics
    output = Path(args.output or str(Path(args.checkpoint).with_name("best_calibrated.pt")))
    output.parent.mkdir(parents=True, exist_ok=True)
    torch.save(checkpoint, output)
    metrics_output = Path(args.metrics_output or output.with_name("calibration_metrics.json"))
    metrics_output.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    print(f"saved={output}; metrics={metrics_output}")


if __name__ == "__main__":
    main()
