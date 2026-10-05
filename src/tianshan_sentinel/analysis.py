from __future__ import annotations

from dataclasses import asdict, dataclass

import cv2
import numpy as np


@dataclass(slots=True)
class ChangeRegion:
    region_id: int
    x: int
    y: int
    width: int
    height: int
    area_pixels: int
    area_ratio: float
    mean_confidence: float
    risk_level: str


def _risk_level(area_ratio: float, confidence: float) -> str:
    score = min(area_ratio * 20.0, 1.0) * 0.65 + confidence * 0.35
    if score >= 0.72:
        return "high"
    if score >= 0.42:
        return "medium"
    return "low"


def analyze_probability(probability: np.ndarray, threshold: float = 0.5, min_region_pixels: int = 40):
    if probability.ndim != 2:
        raise ValueError("Probability map must be two-dimensional")
    binary = (probability >= threshold).astype(np.uint8)
    kernel = np.ones((3, 3), dtype=np.uint8)
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    total_pixels = float(binary.size)
    regions: list[ChangeRegion] = []
    for label_id in range(1, count):
        x, y, width, height, area = [int(value) for value in stats[label_id]]
        if area < min_region_pixels:
            continue
        region_mask = labels == label_id
        confidence = float(probability[region_mask].mean())
        area_ratio = area / total_pixels
        regions.append(
            ChangeRegion(
                region_id=len(regions) + 1,
                x=x,
                y=y,
                width=width,
                height=height,
                area_pixels=area,
                area_ratio=round(area_ratio, 6),
                mean_confidence=round(confidence, 4),
                risk_level=_risk_level(area_ratio, confidence),
            )
        )
    regions.sort(key=lambda item: item.area_pixels, reverse=True)
    for index, region in enumerate(regions, start=1):
        region.region_id = index

    change_ratio = float(binary.sum() / total_pixels)
    mean_confidence = float(probability[binary > 0].mean()) if binary.any() else float(1.0 - probability.mean())
    high_risk = sum(region.risk_level == "high" for region in regions)
    if change_ratio >= 0.18 or high_risk:
        overall_risk = "high"
    elif change_ratio >= 0.06 or len(regions) >= 4:
        overall_risk = "medium"
    else:
        overall_risk = "low"
    if not regions:
        narrative = "未发现达到面积阈值的显著变化斑块，建议结合原始影像分辨率进行例行复核。"
    else:
        narrative = (
            f"检测到 {len(regions)} 个有效变化斑块，变化像素占比 {change_ratio:.2%}，"
            f"综合风险等级为{ {'high': '高', 'medium': '中', 'low': '低'}[overall_risk] }。"
            "建议优先复核面积大、置信度高的区域，并结合地理底图和现场资料确认变化性质。"
        )
    return {
        "change_ratio": round(change_ratio, 6),
        "mean_confidence": round(mean_confidence, 4),
        "region_count": len(regions),
        "overall_risk": overall_risk,
        "narrative": narrative,
        "regions": [asdict(region) for region in regions],
        "mask": binary,
    }


def create_overlay(after_rgb: np.ndarray, probability: np.ndarray, threshold: float = 0.5) -> np.ndarray:
    after_rgb = np.asarray(after_rgb, dtype=np.uint8)
    mask = probability >= threshold
    overlay = after_rgb.copy().astype(np.float32)
    color = np.zeros_like(overlay)
    color[..., 0] = 235
    color[..., 1] = 69
    color[..., 2] = 45
    alpha = np.clip(probability[..., None] * 0.72, 0.0, 0.72)
    overlay[mask] = overlay[mask] * (1.0 - alpha[mask]) + color[mask] * alpha[mask]
    return np.clip(overlay, 0, 255).astype(np.uint8)

