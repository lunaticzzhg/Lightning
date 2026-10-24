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

class MarketImportChoice(BaseModel):
    provider: str
    product: str
    price_mode: str
    adjustment: str = ''
    reference_date: str = ''
    volume_unit: str
    exchange: str | None = None
    minute_position: str | None = None
    target_dataset_id: str | None = None

class MarketPreviewChoice(BaseModel):
    volume_unit: str
    exchange: str | None = None
    minute_position: str | None = None

class MarketConfirmChoice(MarketImportChoice):
    confirmation: str | None = None

class MarketBar(BaseModel):
    exchange: str
    symbol: str
    time: str
    market_time: str
    open: str
    high: str
    low: str
    close: str
    volume: str

class MarketSearchItem(BaseModel):
    dataset_id: str
    provider: str
    product: str
    market: str
    exchange: str
    period: str
    price_mode: str
    adjustment: str
    reference_date: str
    first: str
    last: str
    has_bars: bool
    warning_count: int
    version_id: str
    version_number: int

class MarketStockCandidate(BaseModel):
    market: str
    exchange: str
    symbol: str

class MarketSearch(BaseModel):
    reason: str
    results: list[MarketSearchItem]

class MarketDraft(BaseModel):
    draft_id: str
    period: str
    market: str
    symbols: list[str]
    count: int
    first: str
    last: str
    needs: list[str]
    needs_exchange: bool
    target_mismatch: bool

class MarketPreview(BaseModel):
    examples: list[MarketBar]
    count: int

class MarketDifference(BaseModel):
    key: str
    old: MarketBar
    new: MarketBar

class MarketComparison(BaseModel):
    status: str
    dataset_id: str | None = None
    version_id: str | None = None
    version_number: int | None = None
    added: int = 0
    changed: int = 0
    affected_first: str | None = None
    affected_last: str | None = None
    page: int = 1
    pages: int = 1
    differences: list[MarketDifference] = []
    confirmation: str | None = None

class MarketPublish(BaseModel):
    status: str
    dataset_id: str
    version_id: str
    version_number: int
    added: int
    changed: int
    affected_first: str | None = None
    affected_last: str | None = None
    symbols: list[str]

class MarketResult(BaseModel):
    status: str
    dataset_id: str | None = None
    version_id: str | None = None
    version_number: int | None = None
    added: int | None = None
    changed: int | None = None
    affected_first: str | None = None
    affected_last: str | None = None
    symbols: list[str] | None = None

class MarketImportFile(BaseModel):
    file_name: str
    created_at: str

class MarketImportRecord(BaseModel):
    provider: str
    product: str
    files: list[MarketImportFile]
    previous_version_id: str | None

class MarketChart(BaseModel):
    version_id: str
    version_number: int
    dataset_id: str
    period: str
    market: str
    exchange: str | None
    provider: str
    product: str
    price_mode: str
    adjustment: str
    reference_date: str
    bars: list[MarketBar]
    warnings: list[dict]

class MarketVersion(BaseModel):
    id: str
    number: int
    created_at: str

class MarketSource(BaseModel):
    id: str
    provider: str
    product: str
