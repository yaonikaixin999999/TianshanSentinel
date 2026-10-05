import json
from zipfile import ZipFile

import numpy as np
from PIL import Image

from backend.app.reporting import build_docx_report, build_geojson, build_pdf_report
from backend.app.repository import AnalysisRepository
from backend.app.settings import settings


def _analysis_payload(project_id: str):
    return {
        "before_url": "/runtime/uploads/before.png",
        "after_url": "/runtime/uploads/after.png",
        "overlay_url": "/runtime/results/overlay.png",
        "engine": "test-engine",
        "aligned": True,
        "change_ratio": 0.18,
        "mean_confidence": 0.91,
        "mean_uncertainty": 0.08,
        "region_count": 1,
        "overall_risk": "high",
        "narrative": "检测到 1 个有效变化斑块。",
        "project_id": project_id,
        "before_label": "2024-06",
        "after_label": "2025-06",
        "review_status": "pending",
        "regions": [
            {
                "region_id": 1,
                "x": 12,
                "y": 16,
                "width": 40,
                "height": 32,
                "area_pixels": 840,
                "area_ratio": 0.18,
                "mean_confidence": 0.91,
                "risk_level": "high",
                "event_type": "demolition",
                "event_label": "疑似拆除清理",
                "event_confidence": 0.74,
                "classification_source": "rule_based_review_hint",
                "review_status": "pending",
                "reviewer_note": "",
                "reviewed_at": None,
            }
        ],
    }


def test_project_timeline_and_region_review(tmp_path):
    repository = AnalysisRepository(tmp_path / "platform.db")
    project = repository.create_project(
        {
            "name": "校园建设监测",
            "description": "测试项目",
            "area_name": "新疆大学",
            "center_lat": 43.77,
            "center_lon": 87.61,
            "alert_threshold": 0.1,
        }
    )
    analysis = repository.create("analysis-1", _analysis_payload(project["id"]))

    timeline = repository.project_timeline(project["id"])
    assert timeline["change_ratios"] == [0.18]
    assert timeline["project"]["alerting"] is True
    assert timeline["project"]["pending_reviews"] == 1

    reviewed = repository.update_region(
        analysis["id"],
        1,
        {
            "event_type": "demolition",
            "event_label": "确认拆除",
            "review_status": "approved",
            "reviewer_note": "影像证据清晰",
        },
    )
    assert reviewed["review_status"] == "completed"
    assert reviewed["regions"][0]["review_status"] == "approved"
    assert reviewed["regions"][0]["reviewer_note"] == "影像证据清晰"


def test_exports_are_valid(tmp_path):
    original_runtime = settings.runtime_dir
    settings.runtime_dir = tmp_path
    try:
        settings.prepare()
        image = np.full((96, 128, 3), 172, dtype=np.uint8)
        Image.fromarray(image).save(settings.upload_dir / "before.png")
        image[24:72, 36:96] = [210, 75, 55]
        Image.fromarray(image).save(settings.upload_dir / "after.png")
        Image.fromarray(image).save(settings.result_dir / "overlay.png")
        project = {
            "id": "project-1",
            "name": "校园建设监测",
            "area_name": "新疆大学",
        }
        analysis = {"id": "analysis-1", "created_at": "2026-07-24T08:00:00+00:00", **_analysis_payload(project["id"])}

        geojson = json.loads(build_geojson(analysis, project).decode("utf-8"))
        assert geojson["type"] == "FeatureCollection"
        assert geojson["features"][0]["geometry"]["type"] == "Polygon"
        assert geojson["features"][0]["properties"]["coordinate_system"] == "image_pixel"

        docx_content = build_docx_report(analysis, project)
        docx_path = tmp_path / "report.docx"
        docx_path.write_bytes(docx_content)
        with ZipFile(docx_path) as archive:
            assert "word/document.xml" in archive.namelist()
            assert "遥感变化检测与研判报告" in archive.read("word/document.xml").decode("utf-8")

        pdf_content = build_pdf_report(analysis, project)
        assert pdf_content.startswith(b"%PDF-")
        assert len(pdf_content) > 4_000
    finally:
        settings.runtime_dir = original_runtime
