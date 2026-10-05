import json
import sys
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest
from PIL import Image

from tianshan_sentinel.analysis import analyze_probability
from tianshan_sentinel.inference import (
    OnnxPredictor,
    _fuse_seeded_structural_change,
    register_after_to_before,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_onnx_predictor_reads_sidecar_metadata(tmp_path, monkeypatch):
    model_path = tmp_path / "model.onnx"
    model_path.write_bytes(b"placeholder")
    model_path.with_suffix(".metadata.json").write_text(
        json.dumps({"image_size": 320, "threshold": 0.43}), encoding="utf-8"
    )

    class FakeSession:
        def __init__(self, path, providers):
            self.path = path
            self.providers = providers

    monkeypatch.setitem(sys.modules, "onnxruntime", SimpleNamespace(InferenceSession=FakeSession))
    predictor = OnnxPredictor(model_path)

    assert predictor.image_size == 320
    assert predictor.threshold == 0.43


def test_onnx_preprocessing_accepts_flipped_views(tmp_path, monkeypatch):
    model_path = tmp_path / "model.onnx"
    model_path.write_bytes(b"placeholder")

    class FakeSession:
        def __init__(self, path, providers):
            pass

    monkeypatch.setitem(sys.modules, "onnxruntime", SimpleNamespace(InferenceSession=FakeSession))
    predictor = OnnxPredictor(model_path, image_size=32)
    image = np.zeros((48, 64, 3), dtype=np.uint8)
    flipped = np.fliplr(image)

    tensor = predictor._tensor(flipped)

    assert tensor.shape == (1, 3, 32, 32)
    assert tensor.flags.c_contiguous


def test_onnx_predictor_tiles_large_images_and_detects_both_temporal_directions(tmp_path, monkeypatch):
    model_path = tmp_path / "model.onnx"
    model_path.write_bytes(b"placeholder")

    class DirectionalSession:
        maximum_batch = 0

        def __init__(self, path, providers):
            pass

        def run(self, outputs, inputs):
            before = inputs["before"]
            after = inputs["after"]
            self.maximum_batch = max(self.maximum_batch, before.shape[0])
            logits = (after[:, :1] - before[:, :1]) * 4.0 - 6.0
            return [logits.astype(np.float32)]

    monkeypatch.setitem(sys.modules, "onnxruntime", SimpleNamespace(InferenceSession=DirectionalSession))
    predictor = OnnxPredictor(model_path, image_size=64, threshold=0.5)
    before = np.full((180, 260, 3), 20, dtype=np.uint8)
    after = before.copy()
    before[24:116, 30:142] = 235

    prediction = predictor.predict(before, after)

    assert prediction.probability.shape == before.shape[:2]
    assert prediction.probability[45:95, 50:120].mean() > 0.9
    assert prediction.probability[135:165, 190:240].mean() < 0.01
    assert predictor.session.maximum_batch > 2


def test_registration_accepts_corresponding_textured_images():
    random = np.random.default_rng(17)
    before = random.integers(0, 256, size=(320, 480, 3), dtype=np.uint8)
    matrix = np.float32([[1, 0, 5], [0, 1, 3]])
    after = cv2.warpAffine(before, matrix, (480, 320), borderMode=cv2.BORDER_REFLECT)

    result = register_after_to_before(before, after)

    assert result.comparable
    assert result.aligned
    assert result.inlier_count >= 15


def test_registration_recognizes_pre_registered_rectangular_images():
    random = np.random.default_rng(23)
    before = random.integers(0, 256, size=(240, 420, 3), dtype=np.uint8)
    after = before.copy()
    after[60:180, 120:320] = 135

    result = register_after_to_before(before, after)

    assert result.comparable
    assert not result.aligned
    assert "已处于配准状态" in result.reason


def test_seeded_structural_fusion_expands_large_removal():
    random = np.random.default_rng(41)
    before = random.integers(40, 220, size=(256, 384, 3), dtype=np.uint8)
    after = before.copy()
    after[52:220, 82:330] = 142
    probability = np.zeros(before.shape[:2], dtype=np.float32)
    probability[80:96, 110:126] = 0.9
    probability[174:192, 274:292] = 0.9
    uncertainty = np.zeros_like(probability)

    fused, _, changed = _fuse_seeded_structural_change(
        before,
        after,
        probability,
        uncertainty,
        threshold=0.46,
    )

    assert changed
    assert (fused >= 0.46).mean() > (probability >= 0.46).mean() * 8
    assert (fused >= 0.46).mean() > 0.08


def test_seeded_structural_fusion_ignores_global_brightness_shift():
    before = np.random.default_rng(43).integers(0, 256, size=(256, 384, 3), dtype=np.uint8)
    after = np.clip(before.astype(np.float32) * 0.65 + 45.0, 0, 255).astype(np.uint8)
    probability = np.zeros(before.shape[:2], dtype=np.float32)
    probability[70:84, 90:104] = 0.9
    probability[170:184, 270:284] = 0.9
    uncertainty = np.zeros_like(probability)

    fused, _, changed = _fuse_seeded_structural_change(
        before,
        after,
        probability,
        uncertainty,
        threshold=0.46,
    )

    assert not changed
    assert np.array_equal(fused, probability)


def test_registration_rejects_unrelated_images():
    first = np.random.default_rng(11).integers(0, 256, size=(320, 480, 3), dtype=np.uint8)
    second = np.random.default_rng(29).integers(0, 256, size=(320, 480, 3), dtype=np.uint8)

    result = register_after_to_before(first, second)

    assert not result.comparable
    assert not result.aligned


def test_registration_accepts_pre_registered_demo_pair():
    before = np.asarray(Image.open(PROJECT_ROOT / "frontend/public/demo/before.png").convert("RGB"))
    after = np.asarray(Image.open(PROJECT_ROOT / "frontend/public/demo/after.png").convert("RGB"))

    result = register_after_to_before(before, after)

    assert result.comparable
    assert not result.aligned
    assert "已处于配准状态" in result.reason


def test_verified_demo_triggers_onnx_change_detection():
    pytest.importorskip("onnxruntime")
    model_path = PROJECT_ROOT / "artifacts/model.onnx"
    if not model_path.is_file():
        pytest.skip("Packaged ONNX artifact is not available")
    before = np.asarray(Image.open(PROJECT_ROOT / "frontend/public/demo/before.png").convert("RGB"))
    after = np.asarray(Image.open(PROJECT_ROOT / "frontend/public/demo/after.png").convert("RGB"))
    registration = register_after_to_before(before, after)

    prediction = OnnxPredictor(model_path).predict(before, registration.image)
    summary = analyze_probability(prediction.probability, prediction.threshold)

    assert 0.03 <= summary["change_ratio"] <= 0.15
    assert summary["region_count"] >= 1
    assert "+structural-fusion" not in prediction.engine


def test_verified_demo_is_invariant_to_temporal_order():
    pytest.importorskip("onnxruntime")
    model_path = PROJECT_ROOT / "artifacts/model.onnx"
    if not model_path.is_file():
        pytest.skip("Packaged ONNX artifact is not available")
    before = np.asarray(Image.open(PROJECT_ROOT / "frontend/public/demo/before.png").convert("RGB"))
    after = np.asarray(Image.open(PROJECT_ROOT / "frontend/public/demo/after.png").convert("RGB"))
    predictor = OnnxPredictor(model_path)

    forward = predictor.predict(before, after)
    reverse = predictor.predict(after, before)

    assert np.allclose(forward.probability, reverse.probability, atol=1e-6)
    assert 0.03 <= (forward.probability >= forward.threshold).mean() <= 0.15
    assert "+structural-fusion" not in forward.engine
