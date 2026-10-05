from __future__ import annotations

from io import BytesIO
from pathlib import Path
from uuid import uuid4

import cv2
import numpy as np
from PIL import Image

from tianshan_sentinel.analysis import analyze_probability, create_overlay
from tianshan_sentinel.inference import (
    HeuristicPredictor,
    OnnxPredictor,
    TorchPredictor,
    register_after_to_before,
)

from .repository import AnalysisRepository
from .settings import settings


class IncomparableImagePairError(ValueError):
    pass


class AnalysisService:
    def __init__(self, repository: AnalysisRepository):
        self.repository = repository
        self.predictor = self._load_predictor()

    @staticmethod
    def _load_predictor():
        if settings.onnx_path.is_file():
            try:
                return OnnxPredictor(settings.onnx_path)
            except Exception as error:
                print(f"ONNX load failed, falling back: {error}")
        if settings.model_path.is_file():
            try:
                return TorchPredictor(settings.model_path)
            except Exception as error:
                print(f"PyTorch checkpoint load failed, falling back: {error}")
        return HeuristicPredictor()

    @staticmethod
    def _decode(content: bytes) -> np.ndarray:
        with Image.open(BytesIO(content)) as image:
            return np.asarray(image.convert("RGB"))

    @staticmethod
    def _save_rgb(array: np.ndarray, path: Path) -> None:
        Image.fromarray(array.astype(np.uint8), mode="RGB").save(path, optimize=True)

    @staticmethod
    def _classify_regions(regions: list[dict], before: np.ndarray, after: np.ndarray) -> list[dict]:
        """Attach a reviewable rule-based event suggestion to each change region."""
        before_gray = cv2.cvtColor(before, cv2.COLOR_RGB2GRAY)
        after_gray = cv2.cvtColor(after, cv2.COLOR_RGB2GRAY)
        for region in regions:
            x, y = region["x"], region["y"]
            x2, y2 = x + region["width"], y + region["height"]
            before_crop = before_gray[y:y2, x:x2]
            after_crop = after_gray[y:y2, x:x2]
            if before_crop.size == 0 or after_crop.size == 0:
                event_type, event_label, confidence = "unclassified", "待判定", 0.0
            else:
                before_edges = cv2.Canny(before_crop, 60, 150).mean() / 255.0
                after_edges = cv2.Canny(after_crop, 60, 150).mean() / 255.0
                edge_delta = after_edges - before_edges
                brightness_delta = float(after_crop.mean() - before_crop.mean())
                if edge_delta >= 0.035:
                    event_type, event_label = "new_construction", "疑似新增建设"
                elif edge_delta <= -0.035:
                    event_type, event_label = "demolition", "疑似拆除清理"
                elif abs(brightness_delta) >= 18:
                    event_type, event_label = "surface_change", "疑似地表改造"
                else:
                    event_type, event_label = "uncertain_change", "其他变化"
                confidence = min(0.88, 0.52 + abs(edge_delta) * 2.2 + abs(brightness_delta) / 255.0)
            region.update(
                {
                    "event_type": event_type,
                    "event_label": event_label,
                    "event_confidence": round(float(confidence), 4),
                    "classification_source": "rule_based_review_hint",
                    "review_status": "pending",
                    "reviewer_note": "",
                    "reviewed_at": None,
                }
            )
        return regions

    def analyze(
        self,
        before_content: bytes,
        after_content: bytes,
        project_id: str | None = None,
        before_label: str = "T1",
        after_label: str = "T2",
    ) -> dict:
        analysis_id = uuid4().hex
        before = self._decode(before_content)
        after = self._decode(after_content)
        registration = register_after_to_before(before, after)
        if not registration.comparable:
            raise IncomparableImagePairError(f"影像不可比较：{registration.reason}")
        aligned_after, aligned = registration.image, registration.aligned
        prediction = self.predictor.predict(before, aligned_after)
        summary = analyze_probability(prediction.probability, prediction.threshold)
        regions = self._classify_regions(summary["regions"], before, aligned_after)
        overlay = create_overlay(aligned_after, prediction.probability, prediction.threshold)

        before_path = settings.upload_dir / f"{analysis_id}_before.png"
        after_path = settings.upload_dir / f"{analysis_id}_after.png"
        overlay_path = settings.result_dir / f"{analysis_id}_overlay.png"
        self._save_rgb(before, before_path)
        self._save_rgb(aligned_after, after_path)
        self._save_rgb(overlay, overlay_path)
        payload = {
            "before_url": f"/runtime/uploads/{before_path.name}",
            "after_url": f"/runtime/uploads/{after_path.name}",
            "overlay_url": f"/runtime/results/{overlay_path.name}",
            "engine": prediction.engine,
            "aligned": aligned,
            "change_ratio": summary["change_ratio"],
            "mean_confidence": summary["mean_confidence"],
            "mean_uncertainty": round(float(prediction.uncertainty.mean()), 4),
            "region_count": summary["region_count"],
            "overall_risk": summary["overall_risk"],
            "narrative": summary["narrative"],
            "regions": regions,
            "project_id": project_id,
            "before_label": before_label.strip() or "T1",
            "after_label": after_label.strip() or "T2",
            "review_status": "pending",
        }
        return self.repository.create(analysis_id, payload)

    @property
    def engine_name(self) -> str:
        return self.predictor.engine_name
