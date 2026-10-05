import numpy as np

from tianshan_sentinel.analysis import analyze_probability, create_overlay


def test_analysis_finds_region_and_risk():
    probability = np.zeros((128, 128), dtype=np.float32)
    probability[20:80, 30:100] = 0.92
    result = analyze_probability(probability, threshold=0.5, min_region_pixels=20)
    assert result["region_count"] == 1
    assert result["change_ratio"] > 0.2
    assert result["overall_risk"] == "high"
    assert result["regions"][0]["mean_confidence"] > 0.9


def test_overlay_preserves_shape():
    image = np.full((32, 48, 3), 100, dtype=np.uint8)
    probability = np.ones((32, 48), dtype=np.float32)
    overlay = create_overlay(image, probability)
    assert overlay.shape == image.shape
    assert overlay.dtype == np.uint8
    assert overlay[..., 0].mean() > image[..., 0].mean()

