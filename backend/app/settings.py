from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TS_", env_file=".env", extra="ignore")

    runtime_dir: Path = Path("./runtime")
    model_path: Path = Path("./artifacts/best.pt")
    onnx_path: Path = Path("./artifacts/model.onnx")
    cors_origins: str = "http://localhost:5173"
    max_upload_mb: int = 20

    @property
    def database_path(self) -> Path:
        return self.runtime_dir / "tianshan_sentinel.db"

    @property
    def upload_dir(self) -> Path:
        return self.runtime_dir / "uploads"

    @property
    def result_dir(self) -> Path:
        return self.runtime_dir / "results"

    def prepare(self) -> None:
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.result_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.prepare()

