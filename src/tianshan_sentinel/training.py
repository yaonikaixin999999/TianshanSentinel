from __future__ import annotations

import hashlib
import json
import random
import time
from pathlib import Path

import numpy as np
import torch
from torch.optim import AdamW
from torch.optim.lr_scheduler import CosineAnnealingLR
from torch.utils.data import DataLoader
from tqdm import tqdm

from .config import ExperimentConfig
from .dataset import ChangeDetectionDataset
from .losses import HybridChangeLoss
from .metrics import BinarySegmentationMetrics
from .model import TianshanSiameseNet


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False


def _loader(config: ExperimentConfig, split: str, shuffle: bool) -> DataLoader:
    dataset = ChangeDetectionDataset(
        config.data.root,
        split,
        config.data.image_size,
        augment=split == "train",
        domain_augment=config.data.domain_augment,
        time_swap_probability=config.data.time_swap_probability,
        photometric_probability=config.data.photometric_probability,
        photometric_strength=config.data.photometric_strength,
        shadow_probability=config.data.shadow_probability,
        blur_probability=config.data.blur_probability,
    )
    return DataLoader(
        dataset,
        batch_size=config.data.batch_size,
        shuffle=shuffle,
        num_workers=config.data.num_workers,
        pin_memory=torch.cuda.is_available(),
        persistent_workers=config.data.num_workers > 0,
    )


def run_epoch(model, loader, criterion, device, threshold: float, optimizer=None, amp: bool = True):
    training = optimizer is not None
    model.train(training)
    metrics = BinarySegmentationMetrics(threshold=threshold)
    losses: list[float] = []
    scaler = torch.amp.GradScaler("cuda", enabled=training and amp and device.type == "cuda")
    context = torch.enable_grad if training else torch.no_grad

    with context():
        for batch in tqdm(loader, leave=False, desc="train" if training else "validate"):
            before = batch["before"].to(device, non_blocking=True)
            after = batch["after"].to(device, non_blocking=True)
            target = batch["mask"].to(device, non_blocking=True)
            if training:
                optimizer.zero_grad(set_to_none=True)
            with torch.autocast(device_type=device.type, enabled=amp and device.type == "cuda"):
                logits = model(before, after)
                loss, _ = criterion(logits, target)
            if training:
                scaler.scale(loss).backward()
                scaler.unscale_(optimizer)
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                scaler.step(optimizer)
                scaler.update()
            losses.append(float(loss.detach()))
            metrics.update(logits.detach(), target)
    return {"loss": float(np.mean(losses)), **metrics.compute()}


def train_experiment(config: ExperimentConfig, device_name: str | None = None) -> dict:
    seed_everything(config.seed)
    device = torch.device(device_name or ("cuda" if torch.cuda.is_available() else "cpu"))
    output_dir = Path(config.output_directory)
    output_dir.mkdir(parents=True, exist_ok=True)
    initial_checkpoint = Path(config.train.init_checkpoint) if config.train.init_checkpoint else None
    model = TianshanSiameseNet(
        pretrained=config.model.pretrained and initial_checkpoint is None,
        dropout=config.model.dropout,
    ).to(device)
    source_epoch = 0
    source_sha256 = None
    if initial_checkpoint is not None:
        checkpoint = torch.load(initial_checkpoint, map_location=device, weights_only=False)
        model.load_state_dict(checkpoint["model"])
        source_epoch = int(checkpoint.get("epoch", 0))
        source_sha256 = hashlib.sha256(initial_checkpoint.read_bytes()).hexdigest()
    criterion = HybridChangeLoss(**config.train.loss_weights)
    optimizer = AdamW(model.parameters(), lr=config.train.learning_rate, weight_decay=config.train.weight_decay)
    scheduler = CosineAnnealingLR(optimizer, T_max=max(config.train.epochs, 1), eta_min=1e-6)
    train_loader = _loader(config, "train", True)
    val_loader = _loader(config, "val", False)
    history: list[dict] = []
    baseline_metrics = run_epoch(
        model, val_loader, criterion, device, config.train.threshold, None, config.train.amp
    )
    best_iou = baseline_metrics["iou"]
    best_epoch = source_epoch
    stale_epochs = 0
    started = time.time()

    baseline_checkpoint = {
        "model": model.state_dict(),
        "model_config": {"encoder": config.model.encoder, "dropout": config.model.dropout},
        "epoch": source_epoch,
        "threshold": config.train.threshold,
        "temperature": 1.0,
        "metrics": baseline_metrics,
        "fine_tuning": {
            "source_checkpoint": str(initial_checkpoint) if initial_checkpoint else None,
            "source_sha256": source_sha256,
            "baseline_val_iou": best_iou,
            "additional_epochs": 0,
        },
    }
    torch.save(baseline_checkpoint, output_dir / "best.pt")

    for epoch in range(1, config.train.epochs + 1):
        train_metrics = run_epoch(
            model, train_loader, criterion, device, config.train.threshold, optimizer, config.train.amp
        )
        val_metrics = run_epoch(model, val_loader, criterion, device, config.train.threshold, None, config.train.amp)
        scheduler.step()
        absolute_epoch = source_epoch + epoch
        row = {
            "epoch": absolute_epoch,
            "fine_tune_epoch": epoch,
            "learning_rate": optimizer.param_groups[0]["lr"],
            "train": train_metrics,
            "val": val_metrics,
        }
        history.append(row)
        print(json.dumps(row, ensure_ascii=False))
        checkpoint = {
            "model": model.state_dict(),
            "model_config": {"encoder": config.model.encoder, "dropout": config.model.dropout},
            "epoch": absolute_epoch,
            "threshold": config.train.threshold,
            "temperature": 1.0,
            "metrics": val_metrics,
            "fine_tuning": {
                "source_checkpoint": str(initial_checkpoint) if initial_checkpoint else None,
                "source_sha256": source_sha256,
                "baseline_val_iou": baseline_metrics["iou"],
                "additional_epochs": epoch,
            },
        }
        torch.save(checkpoint, output_dir / "last.pt")
        if val_metrics["iou"] > best_iou:
            best_iou = val_metrics["iou"]
            best_epoch = absolute_epoch
            stale_epochs = 0
            torch.save(checkpoint, output_dir / "best.pt")
        else:
            stale_epochs += 1
        (output_dir / "history.json").write_text(
            json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        if stale_epochs >= config.train.patience:
            break

    summary = {
        "device": str(device),
        "gpu": torch.cuda.get_device_name(device) if device.type == "cuda" else None,
        "torch_version": torch.__version__,
        "cuda_version": torch.version.cuda,
        "seed": config.seed,
        "image_size": config.data.image_size,
        "batch_size": config.data.batch_size,
        "train_samples": len(train_loader.dataset),
        "val_samples": len(val_loader.dataset),
        "epochs_requested": config.train.epochs,
        "training_mode": "incremental_fine_tune" if initial_checkpoint else "from_scratch",
        "source_checkpoint": str(initial_checkpoint) if initial_checkpoint else None,
        "source_checkpoint_sha256": source_sha256,
        "source_checkpoint_epoch": source_epoch if initial_checkpoint else None,
        "baseline_val_metrics": baseline_metrics,
        "domain_augmentation": {
            "enabled": config.data.domain_augment,
            "time_swap_probability": config.data.time_swap_probability,
            "photometric_probability": config.data.photometric_probability,
            "photometric_strength": config.data.photometric_strength,
            "shadow_probability": config.data.shadow_probability,
            "blur_probability": config.data.blur_probability,
        },
        "best_val_iou": best_iou,
        "best_epoch": best_epoch,
        "improved_over_source": best_iou > baseline_metrics["iou"] + 1e-12,
        "epochs_completed": len(history),
        "elapsed_seconds": round(time.time() - started, 2),
        "peak_gpu_memory_mb": (
            round(torch.cuda.max_memory_allocated(device) / (1024**2), 2) if device.type == "cuda" else None
        ),
        "best_checkpoint": str(output_dir / "best.pt"),
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary
