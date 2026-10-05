from io import BytesIO

import numpy as np
from fastapi.testclient import TestClient
from PIL import Image

from backend.app.main import app


def _png(array: np.ndarray) -> bytes:
    stream = BytesIO()
    Image.fromarray(array).save(stream, format="PNG")
    return stream.getvalue()


def test_health_and_analysis_round_trip():
    client = TestClient(app)
    health = client.get("/api/v1/health")
    assert health.status_code == 200
    before = np.random.default_rng(7).integers(0, 256, size=(192, 256, 3), dtype=np.uint8)
    after = before.copy()
    after[60:130, 80:170] = [210, 205, 190]
    response = client.post(
        "/api/v1/analyses",
        data={
            "project_id": "historical-monitoring",
            "before_label": "2024-06",
            "after_label": "2025-06",
        },
        files={
            "before": ("before.png", _png(before), "image/png"),
            "after": ("after.png", _png(after), "image/png"),
        },
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["engine"]
    assert payload["project_id"] == "historical-monitoring"
    assert payload["before_label"] == "2024-06"
    assert payload["after_label"] == "2025-06"
    assert 0.0 <= payload["change_ratio"] <= 1.0
    assert client.get(f"/api/v1/analyses/{payload['id']}").status_code == 200


def test_analysis_rejects_unrelated_images():
    client = TestClient(app)
    before = np.random.default_rng(13).integers(0, 256, size=(192, 256, 3), dtype=np.uint8)
    after = np.random.default_rng(31).integers(0, 256, size=(192, 256, 3), dtype=np.uint8)

    response = client.post(
        "/api/v1/analyses",
        files={
            "before": ("before.png", _png(before), "image/png"),
            "after": ("after.png", _png(after), "image/png"),
        },
    )

    assert response.status_code == 422
    assert "影像不可比较" in response.json()["detail"]
