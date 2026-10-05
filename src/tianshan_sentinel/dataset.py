from __future__ import annotations

import random
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageFilter
from torch.utils.data import Dataset

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff"}
IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def _photometric_jitter(image: np.ndarray, strength: float) -> np.ndarray:
    brightness = random.uniform(1.0 - strength, 1.0 + strength)
    contrast = random.uniform(1.0 - strength, 1.0 + strength)
    saturation = random.uniform(1.0 - strength, 1.0 + strength)
    channel_gain = np.array(
        [random.uniform(1.0 - strength * 0.45, 1.0 + strength * 0.45) for _ in range(3)],
        dtype=np.float32,
    )
    result = image * brightness
    mean = result.mean(axis=(0, 1), keepdims=True)
    result = (result - mean) * contrast + mean
    gray = result.mean(axis=2, keepdims=True)
    result = gray + (result - gray) * saturation
    return np.clip(result * channel_gain, 0.0, 1.0).astype(np.float32, copy=False)


def _soft_shadow(image: np.ndarray) -> np.ndarray:
    height, width = image.shape[:2]
    center_x = random.uniform(0.15, 0.85) * width
    center_y = random.uniform(0.15, 0.85) * height
    radius_x = random.uniform(0.25, 0.65) * width
    radius_y = random.uniform(0.18, 0.50) * height
    angle = random.uniform(0.0, np.pi)
    y, x = np.ogrid[:height, :width]
    x_offset = x - center_x
    y_offset = y - center_y
    rotated_x = x_offset * np.cos(angle) + y_offset * np.sin(angle)
    rotated_y = -x_offset * np.sin(angle) + y_offset * np.cos(angle)
    distance = (rotated_x / radius_x) ** 2 + (rotated_y / radius_y) ** 2
    softness = np.clip(1.0 - distance, 0.0, 1.0) ** 0.6
    darkness = random.uniform(0.18, 0.45)
    return np.clip(image * (1.0 - darkness * softness[..., None]), 0.0, 1.0).astype(
        np.float32, copy=False
    )


def _gaussian_blur(image: np.ndarray) -> np.ndarray:
    radius = random.uniform(0.35, 1.15)
    uint8_image = np.clip(image * 255.0, 0, 255).astype(np.uint8)
    blurred = Image.fromarray(uint8_image).filter(ImageFilter.GaussianBlur(radius=radius))
    return np.asarray(blurred, dtype=np.float32) / 255.0


def _image_paths(directory: Path) -> dict[str, Path]:
    return {
        path.stem: path
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    }


class ChangeDetectionDataset(Dataset):
    """Paired-image dataset using split/A, split/B and split/label folders."""

    def __init__(
        self,
        root: str | Path,
        split: str,
        image_size: int = 256,
        augment: bool = False,
        domain_augment: bool = False,
        time_swap_probability: float = 0.0,
        photometric_probability: float = 0.0,
        photometric_strength: float = 0.2,
        shadow_probability: float = 0.0,
        blur_probability: float = 0.0,
    ):
        self.root = Path(root)
        self.split = split
        self.image_size = image_size
        self.augment = augment
        self.domain_augment = domain_augment and augment
        self.time_swap_probability = time_swap_probability
        self.photometric_probability = photometric_probability
        self.photometric_strength = photometric_strength
        self.shadow_probability = shadow_probability
        self.blur_probability = blur_probability
        split_dir = self.root / split
        required = [split_dir / "A", split_dir / "B", split_dir / "label"]
        missing = [str(path) for path in required if not path.is_dir()]
        if missing:
            raise FileNotFoundError(f"Missing dataset directories: {', '.join(missing)}")

        before = _image_paths(required[0])
        after = _image_paths(required[1])
        labels = _image_paths(required[2])
        names = sorted(before.keys() & after.keys() & labels.keys())
        if not names:
            raise ValueError(f"No matched image triplets found under {split_dir}")
        self.samples = [(before[name], after[name], labels[name]) for name in names]

    def __len__(self) -> int:
        return len(self.samples)

    @staticmethod
    def _resize_triplet(before: Image.Image, after: Image.Image, mask: Image.Image, size: int):
        target = (size, size)
        return (
            before.resize(target, Image.Resampling.BILINEAR),
            after.resize(target, Image.Resampling.BILINEAR),
            mask.resize(target, Image.Resampling.NEAREST),
        )

    def __getitem__(self, index: int) -> dict[str, torch.Tensor | str]:
        before_path, after_path, mask_path = self.samples[index]
        before = Image.open(before_path).convert("RGB")
        after = Image.open(after_path).convert("RGB")
        mask = Image.open(mask_path).convert("L")
        before, after, mask = self._resize_triplet(before, after, mask, self.image_size)

        before_np = np.asarray(before, dtype=np.float32) / 255.0
        after_np = np.asarray(after, dtype=np.float32) / 255.0
        mask_np = (np.asarray(mask, dtype=np.float32) >= 127.5).astype(np.float32)

        if self.augment:
            if random.random() < 0.5:
                before_np = np.fliplr(before_np)
                after_np = np.fliplr(after_np)
                mask_np = np.fliplr(mask_np)
            if random.random() < 0.5:
                before_np = np.flipud(before_np)
                after_np = np.flipud(after_np)
                mask_np = np.flipud(mask_np)
            rotations = random.randint(0, 3)
            if rotations:
                before_np = np.rot90(before_np, rotations)
                after_np = np.rot90(after_np, rotations)
                mask_np = np.rot90(mask_np, rotations)

            if random.random() < self.time_swap_probability:
                before_np, after_np = after_np, before_np

            if self.domain_augment:
                if random.random() < self.photometric_probability:
                    before_np = _photometric_jitter(before_np, self.photometric_strength)
                if random.random() < self.photometric_probability:
                    after_np = _photometric_jitter(after_np, self.photometric_strength)
                if random.random() < self.shadow_probability:
                    if random.random() < 0.5:
                        before_np = _soft_shadow(before_np)
                    else:
                        after_np = _soft_shadow(after_np)
                if random.random() < self.blur_probability:
                    if random.random() < 0.5:
                        before_np = _gaussian_blur(before_np)
                    else:
                        after_np = _gaussian_blur(after_np)

        before_np = np.ascontiguousarray(
            (before_np - IMAGENET_MEAN) / IMAGENET_STD, dtype=np.float32
        )
        after_np = np.ascontiguousarray(
            (after_np - IMAGENET_MEAN) / IMAGENET_STD, dtype=np.float32
        )
        mask_np = np.ascontiguousarray(mask_np[None, ...])
        return {
            "before": torch.from_numpy(before_np).permute(2, 0, 1),
            "after": torch.from_numpy(after_np).permute(2, 0, 1),
            "mask": torch.from_numpy(mask_np),
            "name": before_path.stem,
        }


def validate_dataset(root: str | Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for split in ("train", "val", "test"):
        counts[split] = len(ChangeDetectionDataset(root, split, image_size=32))
    return counts
