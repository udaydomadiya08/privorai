from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class PrivacyMode(str, Enum):
    HYBRID = "hybrid"
    STRICT = "strict"
    FULLY_LOCAL = "fully_local"


class Detection(BaseModel):
    entity_type: str
    start: int
    end: int
    value: str
    score: float = 1.0
    source: str = "rule"


class Transformation(BaseModel):
    entity_type: str
    original: str
    replacement: str
    strategy: str
    source: str


class SanitizationResult(BaseModel):
    sanitized_text: str
    transformations: list[Transformation]
    detections: list[Detection]


class SearchResult(BaseModel):
    query: str
    provider: str
    results: list[dict[str, Any]] = Field(default_factory=list)


class FileArtifact(BaseModel):
    path: str
    parser: str
    extension: str
    media_type: str
    chars_extracted: int
    chunks: int = 1
    warnings: list[str] = Field(default_factory=list)


class ResidualRisk(BaseModel):
    level: str
    blocked: bool
    reasons: list[str] = Field(default_factory=list)
    sanitized_preview: str = ""


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=3, max_length=128)
    message: str = Field(min_length=1, max_length=12000)
    mode: PrivacyMode = PrivacyMode.HYBRID
    use_web_search: bool = False


class FilePathChatRequest(BaseModel):
    session_id: str = Field(min_length=3, max_length=128)
    path: str = Field(min_length=1, max_length=4096)
    message: str = Field(default="", max_length=12000)
    mode: PrivacyMode = PrivacyMode.HYBRID
    use_web_search: bool = False


class DirectoryChatRequest(BaseModel):
    session_id: str = Field(min_length=3, max_length=128)
    path: str = Field(min_length=1, max_length=4096)
    message: str = Field(default="", max_length=12000)
    mode: PrivacyMode = PrivacyMode.HYBRID
    use_web_search: bool = False
    recursive: bool = True
    max_files: int = Field(default=25, ge=1, le=200)


class JobCreateResponse(BaseModel):
    job_id: str
    status: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    kind: str
    created_at: str
    progress_percent: int = 0
    current_step: str = "queued"
    items_processed: int = 0
    total_items: int = 0
    current_item_label: Optional[str] = None
    current_item_parser: Optional[str] = None
    eta_seconds: Optional[int] = None
    recent_items: list[str] = Field(default_factory=list)
    completed_at: Optional[str] = None
    error: Optional[str] = None
    result: Optional["ChatResponse"] = None


class AuditRecord(BaseModel):
    audit_id: str
    session_id: str
    created_at: str
    provider: str
    mode: PrivacyMode
    cloud_llm_used: bool
    local_llm_used: bool
    sanitized_input: str
    refined_prompt: str
    residual_risk: Optional[ResidualRisk] = None
    artifacts: list[FileArtifact] = Field(default_factory=list)


class AuthContext(BaseModel):
    role: str
    scopes: list[str] = Field(default_factory=list)


class ChatResponse(BaseModel):
    session_id: str
    mode: PrivacyMode
    original_input: str
    sanitized_input: str
    refined_prompt: str
    answer: str
    transformations: list[Transformation]
    detections: list[Detection]
    search: Optional[SearchResult] = None
    artifacts: list[FileArtifact] = Field(default_factory=list)
    residual_risk: Optional[ResidualRisk] = None
    provider: str
    local_llm_used: bool
    cloud_llm_used: bool


class HealthResponse(BaseModel):
    status: str
    local_llm_provider: str
    local_model: str
    cloud_provider: str
    cloud_model: str
    presidio_enabled: bool
    web_search_enabled: bool
    block_cloud_on_residual_risk: bool
    max_outbound_prompt_chars: int
    api_auth_enabled: bool
    admin_audit_access_enabled: bool
    audit_snapshots_enabled: bool
    privacy_logging_enabled: bool
