from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageDraw, ImageFont
from torch.utils.data import DataLoader
from tqdm import tqdm

from tianshan_sentinel.dataset import ChangeDetectionDataset
from tianshan_sentinel.model import load_model_from_checkpoint


def _font(size: int):
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ):
        if Path(path).is_file():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _overlay(image: Image.Image, mask: np.ndarray, color: tuple[int, int, int]) -> Image.Image:
    base = np.asarray(image.convert("RGB"), dtype=np.float32)
    selected = mask.astype(bool)
    base[selected] = base[selected] * 0.45 + np.asarray(color, dtype=np.float32) * 0.55
    return Image.fromarray(np.clip(base, 0, 255).astype(np.uint8))


def _montage(before: Image.Image, after: Image.Image, truth: np.ndarray, prediction: np.ndarray, title: str) -> Image.Image:
    panels = [
        (before.convert("RGB"), "Before"),
        (after.convert("RGB"), "After"),
        (_overlay(after, truth, (30, 190, 90)), "Ground truth"),
        (_overlay(after, prediction, (235, 65, 50)), "Prediction"),
    ]
    width, height = panels[0][0].size
    header_height = 58
    canvas = Image.new("RGB", (width * 4, height + header_height), "white")
    draw = ImageDraw.Draw(canvas)
    font = _font(16)
    for index, (panel, label) in enumerate(panels):
        x = index * width
        canvas.paste(panel, (x, header_height))
        draw.text((x + 8, 9), label, fill=(28, 36, 45), font=font)
    draw.text((8, 34), title, fill=(28, 36, 45), font=font)
    return canvas


def main() -> None:
    parser = argparse.ArgumentParser(description="Export representative qualitative test cases")
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--output-dir", default="artifacts/examples")
    parser.add_argument("--image-size", type=int, default=256)
    parser.add_argument("--batch-size", type=int, default=8)
    args = parser.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model, metadata = load_model_from_checkpoint(args.checkpoint, device)
    dataset = ChangeDetectionDataset(args.data_root, "test", args.image_size)
    loader = DataLoader(dataset, batch_size=args.batch_size, num_workers=2)
    scores: list[tuple[int, str, float]] = []
    offset = 0
    with torch.no_grad():
        for batch in tqdm(loader, desc="score examples"):
            logits = model(batch["before"].to(device), batch["after"].to(device)) / metadata["temperature"]
            predictions = torch.sigmoid(logits).cpu() >= metadata["threshold"]
            truth = batch["mask"] >= 0.5
            for item in range(len(batch["name"])):
                union = (predictions[item] | truth[item]).sum().item()
                truth_pixels = truth[item].sum().item()
                if truth_pixels > 0 and union > 0:
                    intersection = (predictions[item] & truth[item]).sum().item()
                    scores.append((offset + item, batch["name"][item], intersection / union))
            offset += len(batch["name"])

    if not scores:
        raise RuntimeError("No changed test samples were found")
    scores.sort(key=lambda item: item[2])
    selections = {
        "low": scores[round((len(scores) - 1) * 0.05)],
        "lower_quartile": scores[round((len(scores) - 1) * 0.25)],
        "median": scores[round((len(scores) - 1) * 0.50)],
        "upper_quartile": scores[round((len(scores) - 1) * 0.75)],
        "high": scores[round((len(scores) - 1) * 0.90)],
        "near_best": scores[round((len(scores) - 1) * 0.98)],
    }
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    records = {}
    with torch.no_grad():
        for label, (index, name, iou) in selections.items():
            sample = dataset[index]
            logits = model(
                sample["before"].unsqueeze(0).to(device), sample["after"].unsqueeze(0).to(device)
            ) / metadata["temperature"]
            prediction = (torch.sigmoid(logits)[0, 0].cpu().numpy() >= metadata["threshold"])
            truth = sample["mask"][0].numpy() >= 0.5
            before_path, after_path, _ = dataset.samples[index]
            before = Image.open(before_path).convert("RGB").resize((args.image_size, args.image_size))
            after = Image.open(after_path).convert("RGB").resize((args.image_size, args.image_size))
            filename = f"case_{label}.png"
            _montage(before, after, truth, prediction, f"IoU {iou:.3f}").save(output_dir / filename)
            records[label] = {"name": name, "iou": iou, "file": filename}

    result = {
        "selection": "5th, 25th, 50th, 75th, 90th and 98th percentiles among changed test samples",
        "threshold": metadata["threshold"],
        "temperature": metadata["temperature"],
        "eligible_samples": len(scores),
        "cases": records,
    }
    (output_dir / "examples.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
