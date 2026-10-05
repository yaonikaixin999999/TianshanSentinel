from __future__ import annotations

import torch
from torch import nn
from torch.nn import functional as F


def dice_loss(logits: torch.Tensor, target: torch.Tensor, smooth: float = 1.0) -> torch.Tensor:
    probability = torch.sigmoid(logits)
    intersection = (probability * target).sum(dim=(1, 2, 3))
    denominator = probability.sum(dim=(1, 2, 3)) + target.sum(dim=(1, 2, 3))
    return (1.0 - (2.0 * intersection + smooth) / (denominator + smooth)).mean()


def boundary_map(tensor: torch.Tensor) -> torch.Tensor:
    dilation = F.max_pool2d(tensor, kernel_size=3, stride=1, padding=1)
    erosion = -F.max_pool2d(-tensor, kernel_size=3, stride=1, padding=1)
    return (dilation - erosion).clamp(0.0, 1.0)


class HybridChangeLoss(nn.Module):
    def __init__(self, bce: float = 0.5, dice: float = 0.4, boundary: float = 0.1):
        super().__init__()
        self.weights = {"bce": bce, "dice": dice, "boundary": boundary}

    def forward(self, logits: torch.Tensor, target: torch.Tensor) -> tuple[torch.Tensor, dict[str, float]]:
        bce_value = F.binary_cross_entropy_with_logits(logits, target)
        dice_value = dice_loss(logits, target)
        boundary_value = F.l1_loss(boundary_map(torch.sigmoid(logits)), boundary_map(target))
        total = (
            self.weights["bce"] * bce_value
            + self.weights["dice"] * dice_value
            + self.weights["boundary"] * boundary_value
        )
        parts = {
            "bce": float(bce_value.detach()),
            "dice": float(dice_value.detach()),
            "boundary": float(boundary_value.detach()),
        }
        return total, parts

