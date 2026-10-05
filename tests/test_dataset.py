from pathlib import Path

import numpy as np
import pytest
from PIL import Image

torch = pytest.importorskip("torch")

from tianshan_sentinel.dataset import ChangeDetectionDataset


def _write(path: Path, array: np.ndarray):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(array).save(path)


def test_dataset_returns_aligned_tensors(tmp_path):
    for folder in ("A", "B"):
        _write(tmp_path / "train" / folder / "sample.png", np.full((20, 30, 3), 120, dtype=np.uint8))
    mask = np.zeros((20, 30), dtype=np.uint8)
    mask[2:8, 4:11] = 255
    _write(tmp_path / "train" / "label" / "sample.png", mask)
    dataset = ChangeDetectionDataset(tmp_path, "train", image_size=32)
    sample = dataset[0]
    assert tuple(sample["before"].shape) == (3, 32, 32)
    assert tuple(sample["after"].shape) == (3, 32, 32)
    assert tuple(sample["mask"].shape) == (1, 32, 32)
    assert set(sample["mask"].unique().tolist()) <= {0.0, 1.0}


def test_domain_augmentation_preserves_mask_and_shapes(tmp_path):
    before = np.zeros((20, 30, 3), dtype=np.uint8)
    before[..., 0] = 180
    after = np.zeros((20, 30, 3), dtype=np.uint8)
    after[..., 1] = 180
    mask = np.zeros((20, 30), dtype=np.uint8)
    mask[3:12, 5:17] = 255
    _write(tmp_path / "train" / "A" / "sample.png", before)
    _write(tmp_path / "train" / "B" / "sample.png", after)
    _write(tmp_path / "train" / "label" / "sample.png", mask)

    dataset = ChangeDetectionDataset(
        tmp_path,
        "train",
        image_size=32,
        augment=True,
        domain_augment=True,
        time_swap_probability=1.0,
        photometric_probability=1.0,
        shadow_probability=1.0,
        blur_probability=1.0,
    )
    sample = dataset[0]

    assert tuple(sample["before"].shape) == (3, 32, 32)
    assert tuple(sample["after"].shape) == (3, 32, 32)
    assert tuple(sample["mask"].shape) == (1, 32, 32)
    assert set(sample["mask"].unique().tolist()) <= {0.0, 1.0}
    assert sample["before"].dtype == torch.float32
    assert sample["after"].dtype == torch.float32
    assert torch.isfinite(sample["before"]).all()
    assert torch.isfinite(sample["after"]).all()


def test_domain_augmentation_is_disabled_for_validation(tmp_path):
    image = np.full((20, 30, 3), 120, dtype=np.uint8)
    mask = np.zeros((20, 30), dtype=np.uint8)
    for folder in ("A", "B"):
        _write(tmp_path / "val" / folder / "sample.png", image)
    _write(tmp_path / "val" / "label" / "sample.png", mask)
    dataset = ChangeDetectionDataset(
        tmp_path,
        "val",
        image_size=32,
        augment=False,
        domain_augment=True,
        photometric_probability=1.0,
        shadow_probability=1.0,
    )
    sample = dataset[0]
    assert torch.equal(sample["before"], sample["after"])
