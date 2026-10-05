from __future__ import annotations

import torch
from torch import nn
from torch.nn import functional as F


class DifferenceGate(nn.Module):
    def __init__(self, channels: int):
        super().__init__()
        self.gate = nn.Sequential(
            nn.Conv2d(channels * 3, channels, kernel_size=1, bias=False),
            nn.BatchNorm2d(channels),
            nn.ReLU(inplace=True),
            nn.Conv2d(channels, channels, kernel_size=1),
            nn.Sigmoid(),
        )

    def forward(self, before: torch.Tensor, after: torch.Tensor) -> torch.Tensor:
        difference = torch.abs(after - before)
        gate = self.gate(torch.cat([before, after, difference], dim=1))
        return difference * (0.1 + gate)


class UpBlock(nn.Module):
    def __init__(self, in_channels: int, skip_channels: int, out_channels: int, dropout: float):
        super().__init__()
        self.block = nn.Sequential(
            nn.Conv2d(in_channels + skip_channels, out_channels, 3, padding=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
            nn.Dropout2d(dropout),
            nn.Conv2d(out_channels, out_channels, 3, padding=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
        )

    def forward(self, x: torch.Tensor, skip: torch.Tensor) -> torch.Tensor:
        x = F.interpolate(x, size=skip.shape[-2:], mode="bilinear", align_corners=False)
        return self.block(torch.cat([x, skip], dim=1))


class ResNet18Encoder(nn.Module):
    def __init__(self, pretrained: bool):
        super().__init__()
        from torchvision.models import ResNet18_Weights, resnet18

        weights = ResNet18_Weights.DEFAULT if pretrained else None
        backbone = resnet18(weights=weights)
        self.stem = nn.Sequential(backbone.conv1, backbone.bn1, backbone.relu)
        self.pool = backbone.maxpool
        self.layer1 = backbone.layer1
        self.layer2 = backbone.layer2
        self.layer3 = backbone.layer3
        self.layer4 = backbone.layer4

    def forward(self, x: torch.Tensor) -> list[torch.Tensor]:
        x0 = self.stem(x)
        x1 = self.layer1(self.pool(x0))
        x2 = self.layer2(x1)
        x3 = self.layer3(x2)
        x4 = self.layer4(x3)
        return [x0, x1, x2, x3, x4]


class TianshanSiameseNet(nn.Module):
    """Shared encoder, attention-gated multi-scale differences and U-Net decoder."""

    def __init__(self, pretrained: bool = True, dropout: float = 0.15):
        super().__init__()
        self.encoder = ResNet18Encoder(pretrained=pretrained)
        channels = [64, 64, 128, 256, 512]
        self.gates = nn.ModuleList(DifferenceGate(channel) for channel in channels)
        self.up3 = UpBlock(512, 256, 256, dropout)
        self.up2 = UpBlock(256, 128, 128, dropout)
        self.up1 = UpBlock(128, 64, 64, dropout)
        self.up0 = UpBlock(64, 64, 64, dropout)
        self.head = nn.Sequential(
            nn.Conv2d(64, 32, 3, padding=1),
            nn.ReLU(inplace=True),
            nn.Dropout2d(dropout),
            nn.Conv2d(32, 1, kernel_size=1),
        )

    def forward(self, before: torch.Tensor, after: torch.Tensor) -> torch.Tensor:
        before_features = self.encoder(before)
        after_features = self.encoder(after)
        differences = [
            gate(before_feature, after_feature)
            for gate, before_feature, after_feature in zip(self.gates, before_features, after_features)
        ]
        x = self.up3(differences[4], differences[3])
        x = self.up2(x, differences[2])
        x = self.up1(x, differences[1])
        x = self.up0(x, differences[0])
        x = F.interpolate(x, size=before.shape[-2:], mode="bilinear", align_corners=False)
        return self.head(x)


def load_model_from_checkpoint(path: str, device: torch.device | str = "cpu"):
    checkpoint = torch.load(path, map_location=device, weights_only=False)
    model_config = checkpoint.get("model_config", {})
    model = TianshanSiameseNet(pretrained=False, dropout=float(model_config.get("dropout", 0.15)))
    model.load_state_dict(checkpoint["model"])
    model.to(device).eval()
    metadata = {
        "threshold": float(checkpoint.get("threshold", 0.5)),
        "temperature": float(checkpoint.get("temperature", 1.0)),
        "epoch": int(checkpoint.get("epoch", -1)),
        "metrics": checkpoint.get("metrics", {}),
    }
    return model, metadata

