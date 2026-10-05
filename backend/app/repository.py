from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


DEFAULT_PROJECT_ID = "historical-monitoring"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AnalysisRepository:
    def __init__(self, database_path: Path):
        self.database_path = database_path
        self._initialize()

    def _connect(self):
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _ensure_column(connection: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in columns:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS analyses (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    before_url TEXT NOT NULL,
                    after_url TEXT NOT NULL,
                    overlay_url TEXT NOT NULL,
                    engine TEXT NOT NULL,
                    aligned INTEGER NOT NULL,
                    change_ratio REAL NOT NULL,
                    mean_confidence REAL NOT NULL,
                    mean_uncertainty REAL NOT NULL,
                    region_count INTEGER NOT NULL,
                    overall_risk TEXT NOT NULL,
                    narrative TEXT NOT NULL,
                    regions_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL,
                    area_name TEXT NOT NULL,
                    center_lat REAL,
                    center_lon REAL,
                    status TEXT NOT NULL,
                    alert_threshold REAL NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            self._ensure_column(connection, "analyses", "project_id", "TEXT")
            self._ensure_column(connection, "analyses", "before_label", "TEXT NOT NULL DEFAULT 'T1'")
            self._ensure_column(connection, "analyses", "after_label", "TEXT NOT NULL DEFAULT 'T2'")
            self._ensure_column(connection, "analyses", "review_status", "TEXT NOT NULL DEFAULT 'pending'")

            project_count = connection.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
            if project_count == 0:
                now = _utc_now()
                connection.execute(
                    """
                    INSERT INTO projects (
                        id, name, description, area_name, center_lat, center_lon,
                        status, alert_threshold, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        DEFAULT_PROJECT_ID,
                        "历史检测任务",
                        "系统升级前产生的双时相分析记录",
                        "未指定区域",
                        None,
                        None,
                        "active",
                        0.12,
                        now,
                        now,
                    ),
                )
            connection.execute(
                "UPDATE analyses SET project_id = ? WHERE project_id IS NULL OR project_id = ''",
                (DEFAULT_PROJECT_ID,),
            )

    @staticmethod
    def _normalize_regions(regions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        for region in regions:
            region.setdefault("event_type", "unclassified")
            region.setdefault("event_label", "待判定")
            region.setdefault("event_confidence", 0.0)
            region.setdefault("classification_source", "unavailable")
            region.setdefault("review_status", "pending")
            region.setdefault("reviewer_note", "")
            region.setdefault("reviewed_at", None)
        return regions

    @classmethod
    def _row(cls, row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["aligned"] = bool(item["aligned"])
        item["regions"] = cls._normalize_regions(json.loads(item.pop("regions_json")))
        item["before_label"] = item.get("before_label") or "T1"
        item["after_label"] = item.get("after_label") or "T2"
        reviewed = sum(region["review_status"] != "pending" for region in item["regions"])
        item["reviewed_regions"] = reviewed
        item["review_progress"] = round(reviewed / len(item["regions"]), 4) if item["regions"] else 1.0
        return item

    @staticmethod
    def _project_row(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["alert_threshold"] = float(item["alert_threshold"])
        item["analysis_count"] = int(item.get("analysis_count") or 0)
        item["region_count"] = int(item.get("region_count") or 0)
        item["pending_reviews"] = int(item.get("pending_reviews") or 0)
        item["latest_change_ratio"] = float(item.get("latest_change_ratio") or 0.0)
        item["alerting"] = item["latest_change_ratio"] >= item["alert_threshold"] and item["analysis_count"] > 0
        return item

    def create(self, analysis_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        record = {
            "id": analysis_id,
            "created_at": _utc_now(),
            **payload,
        }
        record["project_id"] = payload.get("project_id") or DEFAULT_PROJECT_ID
        record["before_label"] = payload.get("before_label") or "T1"
        record["after_label"] = payload.get("after_label") or "T2"
        record["review_status"] = payload.get("review_status") or "pending"
        with self._connect() as connection:
            project = connection.execute("SELECT id FROM projects WHERE id = ?", (record["project_id"],)).fetchone()
            if project is None:
                raise KeyError(record["project_id"])
            connection.execute(
                """
                INSERT INTO analyses (
                    id, created_at, before_url, after_url, overlay_url, engine,
                    aligned, change_ratio, mean_confidence, mean_uncertainty,
                    region_count, overall_risk, narrative, regions_json,
                    project_id, before_label, after_label, review_status
                ) VALUES (
                    :id, :created_at, :before_url, :after_url, :overlay_url, :engine,
                    :aligned, :change_ratio, :mean_confidence, :mean_uncertainty,
                    :region_count, :overall_risk, :narrative, :regions_json,
                    :project_id, :before_label, :after_label, :review_status
                )
                """,
                {**record, "aligned": int(record["aligned"]), "regions_json": json.dumps(record["regions"], ensure_ascii=False)},
            )
            connection.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (_utc_now(), record["project_id"]))
        return self.get(analysis_id)

    def get(self, analysis_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM analyses WHERE id = ?", (analysis_id,)).fetchone()
        if row is None:
            raise KeyError(analysis_id)
        return self._row(row)

    def list(self, limit: int = 50, project_id: str | None = None) -> list[dict[str, Any]]:
        with self._connect() as connection:
            if project_id:
                rows = connection.execute(
                    "SELECT * FROM analyses WHERE project_id = ? ORDER BY created_at DESC LIMIT ?",
                    (project_id, limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM analyses ORDER BY created_at DESC LIMIT ?", (limit,)
                ).fetchall()
        return [self._row(row) for row in rows]

    def statistics(self) -> dict[str, Any]:
        with self._connect() as connection:
            total = connection.execute("SELECT COUNT(*) FROM analyses").fetchone()[0]
            projects = connection.execute("SELECT COUNT(*) FROM projects WHERE status = 'active'").fetchone()[0]
            averages = connection.execute(
                "SELECT AVG(change_ratio), AVG(mean_confidence), SUM(region_count) FROM analyses"
            ).fetchone()
            risks = connection.execute(
                "SELECT overall_risk, COUNT(*) AS count FROM analyses GROUP BY overall_risk"
            ).fetchall()
            rows = connection.execute("SELECT regions_json FROM analyses").fetchall()
        pending_reviews = 0
        reviewed_regions = 0
        for row in rows:
            regions = self._normalize_regions(json.loads(row["regions_json"]))
            pending_reviews += sum(region["review_status"] == "pending" for region in regions)
            reviewed_regions += sum(region["review_status"] != "pending" for region in regions)
        return {
            "total_analyses": total,
            "active_projects": projects,
            "average_change_ratio": round(averages[0] or 0.0, 6),
            "average_confidence": round(averages[1] or 0.0, 4),
            "total_regions": int(averages[2] or 0),
            "pending_reviews": pending_reviews,
            "reviewed_regions": reviewed_regions,
            "risk_distribution": {row["overall_risk"]: row["count"] for row in risks},
        }

    def list_projects(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    p.*,
                    COUNT(a.id) AS analysis_count,
                    COALESCE(SUM(a.region_count), 0) AS region_count,
                    COALESCE((
                        SELECT a2.change_ratio FROM analyses a2
                        WHERE a2.project_id = p.id ORDER BY a2.created_at DESC LIMIT 1
                    ), 0) AS latest_change_ratio,
                    MAX(a.created_at) AS last_analysis_at
                FROM projects p
                LEFT JOIN analyses a ON a.project_id = p.id
                GROUP BY p.id
                ORDER BY p.updated_at DESC
                """
            ).fetchall()
        projects = [self._project_row(row) for row in rows]
        for project in projects:
            analyses = self.list(200, project["id"])
            project["pending_reviews"] = sum(
                region["review_status"] == "pending"
                for analysis in analyses
                for region in analysis["regions"]
            )
        return projects

    def get_project(self, project_id: str) -> dict[str, Any]:
        projects = {project["id"]: project for project in self.list_projects()}
        if project_id not in projects:
            raise KeyError(project_id)
        return projects[project_id]

    def create_project(self, payload: dict[str, Any]) -> dict[str, Any]:
        project_id = uuid4().hex
        now = _utc_now()
        record = {
            "id": project_id,
            "name": payload["name"].strip(),
            "description": payload.get("description", "").strip(),
            "area_name": payload.get("area_name", "未指定区域").strip() or "未指定区域",
            "center_lat": payload.get("center_lat"),
            "center_lon": payload.get("center_lon"),
            "status": payload.get("status", "active"),
            "alert_threshold": payload.get("alert_threshold", 0.12),
            "created_at": now,
            "updated_at": now,
        }
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO projects (
                    id, name, description, area_name, center_lat, center_lon,
                    status, alert_threshold, created_at, updated_at
                ) VALUES (
                    :id, :name, :description, :area_name, :center_lat, :center_lon,
                    :status, :alert_threshold, :created_at, :updated_at
                )
                """,
                record,
            )
        return self.get_project(project_id)

    def update_project(self, project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        allowed = {"name", "description", "area_name", "center_lat", "center_lon", "status", "alert_threshold"}
        updates = {key: value for key, value in payload.items() if key in allowed and value is not None}
        if not updates:
            return self.get_project(project_id)
        updates["updated_at"] = _utc_now()
        assignments = ", ".join(f"{key} = :{key}" for key in updates)
        with self._connect() as connection:
            cursor = connection.execute(
                f"UPDATE projects SET {assignments} WHERE id = :project_id",
                {**updates, "project_id": project_id},
            )
            if cursor.rowcount == 0:
                raise KeyError(project_id)
        return self.get_project(project_id)

    def project_timeline(self, project_id: str) -> dict[str, Any]:
        project = self.get_project(project_id)
        items = list(reversed(self.list(200, project_id)))
        return {
            "project": project,
            "items": items,
            "labels": [item["after_label"] for item in items],
            "change_ratios": [item["change_ratio"] for item in items],
            "region_counts": [item["region_count"] for item in items],
        }

    def update_region(self, analysis_id: str, region_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        analysis = self.get(analysis_id)
        region = next((item for item in analysis["regions"] if item["region_id"] == region_id), None)
        if region is None:
            raise KeyError(region_id)
        for key in ("event_type", "event_label", "review_status", "reviewer_note"):
            if key in payload and payload[key] is not None:
                region[key] = payload[key]
        region["reviewed_at"] = _utc_now() if region["review_status"] != "pending" else None

        statuses = {item["review_status"] for item in analysis["regions"]}
        review_status = "completed" if "pending" not in statuses else "in_progress" if len(statuses) > 1 else "pending"
        with self._connect() as connection:
            connection.execute(
                "UPDATE analyses SET regions_json = ?, review_status = ? WHERE id = ?",
                (json.dumps(analysis["regions"], ensure_ascii=False), review_status, analysis_id),
            )
        return self.get(analysis_id)
