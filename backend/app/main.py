from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
from PIL import UnidentifiedImageError
from pydantic import BaseModel, Field

from .reporting import build_docx_report, build_geojson, build_pdf_report, build_project_csv
from .repository import AnalysisRepository
from .service import AnalysisService, IncomparableImagePairError
from .settings import settings


class ProjectCreate(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    description: str = Field(default="", max_length=300)
    area_name: str = Field(default="未指定区域", max_length=100)
    center_lat: float | None = Field(default=None, ge=-90, le=90)
    center_lon: float | None = Field(default=None, ge=-180, le=180)
    alert_threshold: float = Field(default=0.12, ge=0, le=1)


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=80)
    description: str | None = Field(default=None, max_length=300)
    area_name: str | None = Field(default=None, max_length=100)
    center_lat: float | None = Field(default=None, ge=-90, le=90)
    center_lon: float | None = Field(default=None, ge=-180, le=180)
    status: Literal["active", "archived"] | None = None
    alert_threshold: float | None = Field(default=None, ge=0, le=1)


class RegionReview(BaseModel):
    event_type: Literal["new_construction", "demolition", "surface_change", "uncertain_change", "unclassified"] | None = None
    event_label: str | None = Field(default=None, max_length=40)
    review_status: Literal["pending", "approved", "rejected"]
    reviewer_note: str = Field(default="", max_length=300)

app = FastAPI(
    title="Tianshan Sentinel API",
    version="1.0.0",
    description="Bi-temporal remote-sensing change analysis and audit API",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/runtime", StaticFiles(directory=settings.runtime_dir), name="runtime")
repository = AnalysisRepository(settings.database_path)
service = AnalysisService(repository)


@app.get("/api/v1/health")
def health():
    return {"status": "ok", "engine": service.engine_name, "version": app.version}


@app.post("/api/v1/analyses", status_code=201)
async def create_analysis(
    before: UploadFile = File(...),
    after: UploadFile = File(...),
    project_id: str | None = Form(default=None),
    before_label: str = Form(default="T1", max_length=40),
    after_label: str = Form(default="T2", max_length=40),
):
    allowed = {"image/png", "image/jpeg", "image/tiff"}
    if before.content_type not in allowed or after.content_type not in allowed:
        raise HTTPException(415, "Only PNG, JPEG and TIFF images are supported")
    before_content, after_content = await before.read(), await after.read()
    maximum = settings.max_upload_mb * 1024 * 1024
    if not before_content or not after_content:
        raise HTTPException(400, "Both images are required")
    if len(before_content) > maximum or len(after_content) > maximum:
        raise HTTPException(413, f"Each image must be <= {settings.max_upload_mb} MB")
    if project_id:
        try:
            repository.get_project(project_id)
        except KeyError as error:
            raise HTTPException(404, "Project not found") from error
    try:
        return service.analyze(before_content, after_content, project_id, before_label, after_label)
    except UnidentifiedImageError as error:
        raise HTTPException(400, "Invalid image content") from error
    except IncomparableImagePairError as error:
        raise HTTPException(422, str(error)) from error


@app.get("/api/v1/analyses")
def list_analyses(
    limit: int = Query(50, ge=1, le=200),
    project_id: str | None = Query(default=None),
):
    return {"items": repository.list(limit, project_id), "limit": limit}


@app.get("/api/v1/analyses/{analysis_id}")
def get_analysis(analysis_id: str):
    try:
        return repository.get(analysis_id)
    except KeyError as error:
        raise HTTPException(404, "Analysis not found") from error


@app.patch("/api/v1/analyses/{analysis_id}/regions/{region_id}")
def review_region(analysis_id: str, region_id: int, review: RegionReview):
    try:
        return repository.update_region(analysis_id, region_id, review.model_dump())
    except KeyError as error:
        raise HTTPException(404, "Analysis or region not found") from error


@app.get("/api/v1/reviews")
def review_queue(status: Literal["pending", "approved", "rejected", "all"] = "pending", limit: int = Query(200, ge=1, le=500)):
    items = []
    projects = {project["id"]: project for project in repository.list_projects()}
    for analysis in repository.list(200):
        for region in analysis["regions"]:
            if status != "all" and region["review_status"] != status:
                continue
            items.append(
                {
                    **region,
                    "analysis_id": analysis["id"],
                    "analysis_created_at": analysis["created_at"],
                    "project_id": analysis["project_id"],
                    "project_name": projects.get(analysis["project_id"], {}).get("name", "未归属项目"),
                    "before_label": analysis["before_label"],
                    "after_label": analysis["after_label"],
                    "overlay_url": analysis["overlay_url"],
                }
            )
    return {"items": items[:limit], "total": len(items), "status": status}


def _analysis_and_project(analysis_id: str):
    try:
        analysis = repository.get(analysis_id)
        project = repository.get_project(analysis["project_id"])
        return analysis, project
    except KeyError as error:
        raise HTTPException(404, "Analysis or project not found") from error


@app.get("/api/v1/analyses/{analysis_id}/exports/regions.geojson")
def export_geojson(analysis_id: str):
    analysis, project = _analysis_and_project(analysis_id)
    return StreamingResponse(
        BytesIO(build_geojson(analysis, project)),
        media_type="application/geo+json",
        headers={"Content-Disposition": f'attachment; filename="regions-{analysis_id[:8]}.geojson"'},
    )


@app.get("/api/v1/analyses/{analysis_id}/exports/report.docx")
def export_docx(analysis_id: str):
    analysis, project = _analysis_and_project(analysis_id)
    return StreamingResponse(
        BytesIO(build_docx_report(analysis, project)),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="sentinel-report-{analysis_id[:8]}.docx"'},
    )


@app.get("/api/v1/analyses/{analysis_id}/exports/report.pdf")
def export_pdf(analysis_id: str):
    analysis, project = _analysis_and_project(analysis_id)
    return StreamingResponse(
        BytesIO(build_pdf_report(analysis, project)),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="sentinel-report-{analysis_id[:8]}.pdf"'},
    )


@app.get("/api/v1/projects")
def list_projects():
    return {"items": repository.list_projects()}


@app.post("/api/v1/projects", status_code=201)
def create_project(project: ProjectCreate):
    return repository.create_project(project.model_dump())


@app.patch("/api/v1/projects/{project_id}")
def update_project(project_id: str, project: ProjectUpdate):
    try:
        return repository.update_project(project_id, project.model_dump(exclude_unset=True))
    except KeyError as error:
        raise HTTPException(404, "Project not found") from error


@app.get("/api/v1/projects/{project_id}/timeline")
def project_timeline(project_id: str):
    try:
        return repository.project_timeline(project_id)
    except KeyError as error:
        raise HTTPException(404, "Project not found") from error


@app.get("/api/v1/projects/{project_id}/exports/timeline.csv")
def export_project_timeline(project_id: str):
    try:
        timeline = repository.project_timeline(project_id)
    except KeyError as error:
        raise HTTPException(404, "Project not found") from error
    return StreamingResponse(
        BytesIO(build_project_csv(timeline)),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="project-{project_id[:8]}-timeline.csv"'},
    )


@app.get("/api/v1/statistics")
def statistics():
    return repository.statistics()


frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
