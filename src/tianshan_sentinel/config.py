from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(slots=True)
class DataConfig:
    root: str
    image_size: int = 256
    num_workers: int = 4
    batch_size: int = 8
    domain_augment: bool = False
    time_swap_probability: float = 0.0
    photometric_probability: float = 0.0
    photometric_strength: float = 0.2
    shadow_probability: float = 0.0
    blur_probability: float = 0.0


@dataclass(slots=True)
class ModelConfig:
    encoder: str = "resnet18"
    pretrained: bool = True
    dropout: float = 0.15


@dataclass(slots=True)
class TrainConfig:
    epochs: int = 80
    learning_rate: float = 3e-4
    weight_decay: float = 1e-4
    amp: bool = True
    patience: int = 12
    threshold: float = 0.5
    init_checkpoint: str | None = None
    loss_weights: dict[str, float] | None = None

    def __post_init__(self) -> None:
        if self.loss_weights is None:
            self.loss_weights = {"bce": 0.5, "dice": 0.4, "boundary": 0.1}


@dataclass(slots=True)
class ExperimentConfig:
    seed: int
    data: DataConfig
    model: ModelConfig
    train: TrainConfig
    output_directory: str


def load_config(path: str | Path) -> ExperimentConfig:
    with Path(path).open("r", encoding="utf-8") as handle:
        raw: dict[str, Any] = yaml.safe_load(handle)
    return ExperimentConfig(
        seed=int(raw.get("project", {}).get("seed", 2026)),
        data=DataConfig(**raw["data"]),
        model=ModelConfig(**raw.get("model", {})),
        train=TrainConfig(**raw.get("train", {})),
        output_directory=raw.get("output", {}).get("directory", "./artifacts/run"),
    )
