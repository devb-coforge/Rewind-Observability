from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field


class SourceConfig(BaseModel):
    path: str
    agent: Literal["claude_code", "codex"] | None = None


class OtelConfig(BaseModel):
    endpoint: str = ""
    include_content: bool = False
    protocol: Literal["http/protobuf", "http/json"] = "http/protobuf"


class BoundaryConfig(BaseModel):
    allow_prefixes: list[str] = Field(default_factory=list)


class AppConfig(BaseModel):
    sources: list[SourceConfig] = Field(default_factory=list)
    data_dir: Path = Path("./data")
    pricing_file: Path | None = None
    static_dir: Path | None = None
    otel: OtelConfig = Field(default_factory=OtelConfig)
    boundary: BoundaryConfig = Field(default_factory=BoundaryConfig)
    ingest_on_startup: bool = True

    model_config = {"arbitrary_types_allowed": True}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def default_pricing_file() -> Path | None:
    env = os.environ.get("OBS_PRICING_FILE")
    candidates = []
    if env:
        candidates.append(Path(env))
    candidates.extend(
        [
            Path("/app/pricing.yaml"),
            _repo_root() / "pricing.yaml",
        ]
    )
    for path in candidates:
        if path.is_file():
            return path
    return None


def default_static_dir() -> Path | None:
    env = os.environ.get("OBS_STATIC_DIR")
    candidates = []
    if env:
        candidates.append(Path(env))
    candidates.extend(
        [
            Path("/app/frontend/dist"),
            _repo_root() / "frontend" / "dist",
        ]
    )
    for path in candidates:
        if path.is_dir():
            return path
    return None


def load_config() -> AppConfig:
    """Load config.yaml plus OBS_* environment overrides."""
    config_path = os.environ.get("OBS_CONFIG")
    data: dict = {}
    if config_path:
        path = Path(config_path)
        if path.is_file():
            loaded = yaml.safe_load(path.read_text()) or {}
            if isinstance(loaded, dict):
                data = loaded
    else:
        for candidate in (Path("config.yaml"), Path("/app/config.yaml")):
            if candidate.is_file():
                loaded = yaml.safe_load(candidate.read_text()) or {}
                if isinstance(loaded, dict):
                    data = loaded
                break

    sources = data.get("sources") or []
    env_sources = os.environ.get("OBS_SOURCES")
    if env_sources:
        sources = [{"path": part.strip()} for part in env_sources.split(",") if part.strip()]

    data_dir = os.environ.get("OBS_DATA_DIR") or data.get("data_dir") or "./data"
    pricing = os.environ.get("OBS_PRICING_FILE") or data.get("pricing_file")
    otel = data.get("otel") or {}
    if os.environ.get("OBS_OTEL_ENDPOINT") is not None:
        otel["endpoint"] = os.environ["OBS_OTEL_ENDPOINT"]
    if os.environ.get("OBS_OTEL_INCLUDE_CONTENT") is not None:
        otel["include_content"] = os.environ["OBS_OTEL_INCLUDE_CONTENT"].lower() in {
            "1",
            "true",
            "yes",
        }
    if os.environ.get("OBS_OTEL_PROTOCOL"):
        otel["protocol"] = os.environ["OBS_OTEL_PROTOCOL"]
    boundary = data.get("boundary") or {}

    return AppConfig(
        sources=[SourceConfig.model_validate(item) for item in sources],
        data_dir=Path(data_dir),
        pricing_file=Path(pricing) if pricing else default_pricing_file(),
        static_dir=default_static_dir(),
        otel=OtelConfig.model_validate(otel),
        boundary=BoundaryConfig.model_validate(boundary),
        ingest_on_startup=True,
    )
