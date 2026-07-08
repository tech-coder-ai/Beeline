"""Request/response DTOs for the REST API (non-pipeline entities)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.response import BeelineResponse


# ---------------------------------------------------------------- chat
class ChatRequest(BaseModel):
    session_id: str | None = None
    message: str
    connector_id: str | None = None
    clarification_answer: str | None = None      # answer to a pending clarification
    execute_preview_id: str | None = None        # confirm a previewed execution


class ChatSessionOut(BaseModel):
    id: str
    title: str
    is_pinned: bool
    is_archived: bool
    is_shared: bool
    share_token: str | None
    created_at: datetime
    updated_at: datetime
    message_count: int = 0

    model_config = {"from_attributes": True}


class ChatMessageOut(BaseModel):
    id: str
    role: str
    content: str | None
    response_payload: dict | None
    execution_id: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatTurnOut(BaseModel):
    session_id: str
    message_id: str
    response: BeelineResponse


class SessionUpdate(BaseModel):
    title: str | None = None
    is_pinned: bool | None = None
    is_archived: bool | None = None
    is_shared: bool | None = None


# ---------------------------------------------------------------- metadata
class ColumnOut(BaseModel):
    id: str
    name: str
    position: int
    data_type: str
    inferred_semantic_type: str | None
    description: str | None
    tags: list | None
    classification: str | None
    is_pii: bool
    is_partition: bool
    null_percentage: float | None
    distinct_count: int | None
    sample_values: list | None
    top_values: list | None

    model_config = {"from_attributes": True}


class TableOut(BaseModel):
    id: str
    name: str
    table_type: str
    description: str | None
    owner: str | None
    steward: str | None
    tags: list | None
    classification: str | None
    row_count: int | None
    size_bytes: int | None
    storage_format: str | None
    partition_columns: list | None
    last_synced_at: datetime | None
    usage_count: int
    database_name: str | None = None
    column_count: int = 0

    model_config = {"from_attributes": True}


class TableDetailOut(TableOut):
    columns: list[ColumnOut] = Field(default_factory=list)


class TableUpdate(BaseModel):
    description: str | None = None
    owner: str | None = None
    steward: str | None = None
    tags: list[str] | None = None
    classification: str | None = None


class ColumnUpdate(BaseModel):
    description: str | None = None
    tags: list[str] | None = None
    classification: str | None = None
    is_pii: bool | None = None


# ---------------------------------------------------------------- glossary
class GlossaryTermIn(BaseModel):
    term: str
    definition: str
    business_meaning: str | None = None
    examples: list[str] = Field(default_factory=list)
    owner: str | None = None
    tags: list[str] = Field(default_factory=list)
    synonyms: list[str] = Field(default_factory=list)


class GlossaryTermOut(GlossaryTermIn):
    id: str
    status: str
    source: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------- approvals
class ApprovalOut(BaseModel):
    id: str
    entity_type: str
    entity_id: str
    entity_label: str
    field: str
    current_value: str | None
    proposed_value: str
    source: str
    confidence: float | None
    rationale: str | None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ApprovalDecision(BaseModel):
    action: Literal["approve", "reject", "edit"]
    edited_value: str | None = None
    note: str | None = None


class BulkApprovalDecision(BaseModel):
    ids: list[str]
    action: Literal["approve", "reject"]
    note: str | None = None


# ---------------------------------------------------------------- dashboards
class WidgetIn(BaseModel):
    title: str
    widget_type: str
    size: str = "half"
    sql: str | None = None
    connector_id: str | None = None
    visualization: dict | None = None
    snapshot: dict | None = None
    source_execution_id: str | None = None


class WidgetOut(WidgetIn):
    id: str
    position: int

    model_config = {"from_attributes": True}


class DashboardIn(BaseModel):
    name: str
    description: str | None = None
    refresh_interval_seconds: int | None = None


class DashboardOut(DashboardIn):
    id: str
    is_shared: bool
    share_token: str | None
    created_at: datetime
    updated_at: datetime
    widgets: list[WidgetOut] = Field(default_factory=list)

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------- queries
class SavedQueryIn(BaseModel):
    name: str
    description: str | None = None
    sql: str
    connector_id: str | None = None
    prompt: str | None = None
    tags: list[str] = Field(default_factory=list)


class SavedQueryOut(SavedQueryIn):
    id: str
    is_bookmarked: bool
    last_run_at: datetime | None
    run_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------- sql
class SqlExecuteRequest(BaseModel):
    sql: str
    connector_id: str | None = None
    limit: int | None = None


class SqlValidateRequest(BaseModel):
    sql: str
    connector_id: str | None = None


# ---------------------------------------------------------------- feedback
class FeedbackIn(BaseModel):
    execution_id: str | None = None
    message_id: str | None = None
    rating: Literal["up", "down"]
    category: str | None = None
    comment: str | None = None
    corrected_sql: str | None = None


# ---------------------------------------------------------------- admin
class ConfigUpdate(BaseModel):
    key: str
    value: Any


class ConnectorTestResult(BaseModel):
    ok: bool
    message: str
    latency_ms: int | None = None


class SyncRequest(BaseModel):
    connector_id: str | None = None
    mode: Literal["full", "incremental"] = "incremental"


class EnrichRequest(BaseModel):
    table_ids: list[str] = Field(default_factory=list)  # empty = all pending
