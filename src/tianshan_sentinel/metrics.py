from __future__ import annotations

from dataclasses import dataclass

import torch


@dataclass
class BinarySegmentationMetrics:
    threshold: float = 0.5
    tp: int = 0
    fp: int = 0
    fn: int = 0
    tn: int = 0

    def update(self, logits: torch.Tensor, target: torch.Tensor) -> None:
        prediction = torch.sigmoid(logits) >= self.threshold
        truth = target >= 0.5
        self.tp += int((prediction & truth).sum().item())
        self.fp += int((prediction & ~truth).sum().item())
        self.fn += int((~prediction & truth).sum().item())
        self.tn += int((~prediction & ~truth).sum().item())

    def compute(self) -> dict[str, float]:
        epsilon = 1e-8
        precision = self.tp / (self.tp + self.fp + epsilon)
        recall = self.tp / (self.tp + self.fn + epsilon)
        iou = self.tp / (self.tp + self.fp + self.fn + epsilon)
        f1 = 2 * precision * recall / (precision + recall + epsilon)
        accuracy = (self.tp + self.tn) / (self.tp + self.fp + self.fn + self.tn + epsilon)
        return {
            "precision": precision,
            "recall": recall,
            "iou": iou,
            "f1": f1,
            "accuracy": accuracy,
        }

