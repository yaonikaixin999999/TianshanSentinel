from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import DataLoader
from tqdm import tqdm

from tianshan_sentinel.dataset import ChangeDetectionDataset
from tianshan_sentinel.metrics import BinarySegmentationMetrics
from tianshan_sentinel.model import load_model_from_checkpoint


PROFILES = {
    "clean": {},
    "photometric": {
        "augment": True,
        "domain_augment": True,
        "time_swap_probability": 0.5,
        "photometric_probability": 1.0,
        "photometric_strength": 0.22,
    },
    "shadow": {
        "augment": True,
        "domain_augment": True,
        "time_swap_probability": 0.5,
        "shadow_probability": 1.0,
    },
    "mixed": {
        "augment": True,
        "domain_augment": True,
        "time_swap_probability": 0.5,
        "photometric_probability": 0.8,
        "photometric_strength": 0.22,
        "shadow_probability": 0.3,
        "blur_probability": 0.15,
    },
}


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def evaluate_profile(
    model,
    metadata: dict,
    data_root: str,
    split: str,
    image_size: int,
    batch_size: int,
    device: torch.device,
    profile: str,
    seed: int,
) -> dict[str, float]:
    seed_everything(seed)
    dataset = ChangeDetectionDataset(
        data_root,
        split,
        image_size,
        **PROFILES[profile],
    )
    loader = DataLoader(dataset, batch_size=batch_size, num_workers=0, pin_memory=device.type == "cuda")
    metrics = BinarySegmentationMetrics(metadata["threshold"])
    with torch.no_grad():
        for batch in tqdm(loader, desc=profile, leave=False):
            logits = model(
                batch["before"].to(device, non_blocking=True),
                batch["after"].to(device, non_blocking=True),
            ) / metadata["temperature"]
            metrics.update(logits.cpu(), batch["mask"])
    return metrics.compute()


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate clean and domain-shift robustness")
    parser.add_argument(
        "--checkpoint",
        action="append",
        required=True,
        help="Checkpoint as NAME=PATH; repeat to compare models",
    )
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--split", default="val")
    parser.add_argument("--image-size", type=int, default=256)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    results = {
        "dataset_split": args.split,
        "seed": args.seed,
        "profiles": list(PROFILES),
        "models": {},
    }
    for specification in args.checkpoint:
        if "=" not in specification:
            raise ValueError("--checkpoint must use NAME=PATH")
        name, checkpoint_path = specification.split("=", 1)
        model, metadata = load_model_from_checkpoint(checkpoint_path, device)
        profile_metrics = {
            profile: evaluate_profile(
                model,
                metadata,
                args.data_root,
                args.split,
                args.image_size,
                args.batch_size,
                device,
                profile,
                args.seed,
            )
            for profile in PROFILES
        }
        robust_mean_iou = float(
            np.mean([profile_metrics[name]["iou"] for name in PROFILES if name != "clean"])
        )
        results["models"][name] = {
            "checkpoint": checkpoint_path,
            "threshold": metadata["threshold"],
            "temperature": metadata["temperature"],
            "metrics": profile_metrics,
            "clean_iou": profile_metrics["clean"]["iou"],
            "robust_mean_iou": robust_mean_iou,
            "composite_iou": 0.5 * profile_metrics["clean"]["iou"] + 0.5 * robust_mean_iou,
        }
        del model
        if device.type == "cuda":
            torch.cuda.empty_cache()

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
