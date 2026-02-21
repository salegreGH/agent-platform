from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


RunStatus = Literal["pending", "running", "blocked", "completed", "failed"]
StepStatus = Literal["pending", "running", "blocked", "completed", "failed", "retrying"]
ProposalStatus = Literal["proposed", "approved", "applied", "failed", "rolled_back"]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ActionCall(BaseModel):
    agent_id: str
    action: str
    args: Dict[str, Any] = Field(default_factory=dict)
    expected_output_schema: Dict[str, Any] = Field(default_factory=dict)


class RunStep(BaseModel):
    id: str
    kind: Literal["api", "browser", "llm", "validation", "compose"] = "compose"
    agent: str
    action: str
    status: StepStatus = "pending"
    retries: int = 0
    inputs: Dict[str, Any] = Field(default_factory=dict)
    outputs: Dict[str, Any] = Field(default_factory=dict)
    dependencies: List[str] = Field(default_factory=list)
    requires_confirmation: bool = False
    data_sensitivity: Literal["low", "medium", "high"] = "low"
    error: Optional[str] = None


class Run(BaseModel):
    run_id: str
    goal: str
    status: RunStatus = "pending"
    steps: List[RunStep] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class Proposal(BaseModel):
    proposal_id: str
    title: str
    file_path: str
    content: str
    status: ProposalStatus = "proposed"
    security_notes: List[str] = Field(default_factory=list)
    rollback_plan: List[str] = Field(default_factory=list)


class ConnectorConfig(BaseModel):
    connector_id: str
    enabled: bool = True
    auth_mode: str = "api_key"
    scopes: List[str] = Field(default_factory=list)
    settings: Dict[str, Any] = Field(default_factory=dict)
    rate_limit_per_minute: Optional[int] = None
    retry_count: int = 2
    cache_ttl_seconds: Optional[int] = None


class BrowserAction(BaseModel):
    action: Literal[
        "open_url",
        "click",
        "type",
        "scroll",
        "select",
        "wait_for",
        "screenshot",
        "extract_text",
    ]
    selector: Optional[str] = None
    value: Optional[str] = None
    timeout_ms: int = 10_000


class BrowserSession(BaseModel):
    session_id: str
    status: Literal["created", "open", "paused_login", "ready", "running", "error", "completed", "failed"] = "created"
    current_url: Optional[str] = None
    pause_reason: Optional[str] = None
    login_detected: bool = False
    last_screenshot: Optional[str] = None
    last_error_code: Optional[str] = None
    selectors: Dict[str, list[str]] = Field(default_factory=dict)
    last_action_log: List[Dict[str, Any]] = Field(default_factory=list)
    trace: List[Dict[str, Any]] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=utc_now)
