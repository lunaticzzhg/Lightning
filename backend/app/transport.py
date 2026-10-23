"""HTTP response models used by the management API."""
from __future__ import annotations
from pydantic import BaseModel, ConfigDict
from backend.features.strategies.manifest import Manifest

class Strategy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    name: str
    version_count: int
    latest_version: int | None

class Version(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    strategy_id: str
    number: int
    file_name: str
    uploaded_at: str
    sha256: str
    manifest: Manifest
    status: str

class StrategyDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")
    strategy: Strategy
    versions: list[Version]

class VersionDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Version
    strategy: Strategy

class Error(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    message: str

class Status(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ok: bool
    token: str
