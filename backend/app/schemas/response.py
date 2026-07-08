"""BeelineResponse: the structured contract for every assistant answer.

The LLM never returns HTML, markdown tables, or UI. Every pipeline run produces
this schema and the Angular adaptive renderer decides how to display it.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

VisualizationType = Literal[
    "text", "grid", "kpi", "line", "area", "bar", "pie", "donut",
    "scatter", "heatmap", "treemap", "pivot", "mixed",
]


class ConfidenceBreakdown(BaseModel):
    business: float = 0.0
    metadata: float = 0.0
    sql: float = 0.0
    overall: float = 0.0


class KpiCard(BaseModel):
    label: str
    value: str
    raw_value: float | None = None
    unit: str | None = None
    trend: float | None = None            # +/- percent vs comparison period
    trend_label: str | None = None
    severity: Literal["neutral", "good", "warning", "bad"] = "neutral"


class ChartSeries(BaseModel):
    name: str
    data: list[Any]
    type: str | None = None               # override per-series (combo charts)


class ChartSpec(BaseModel):
    chart_type: Literal["line", "area", "bar", "pie", "donut", "scatter", "heatmap", "treemap"]
    title: str | None = None
    categories: list[Any] = Field(default_factory=list)   # x-axis / labels
    series: list[ChartSeries] = Field(default_factory=list)
    x_label: str | None = None
    y_label: str | None = None
    stacked: bool = False


class TableColumn(BaseModel):
    field: str
    header: str
    data_type: str = "string"             # string|number|date|boolean|currency|percent
    is_metric: bool = False


class TableSpec(BaseModel):
    columns: list[TableColumn] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    total_rows: int = 0
    truncated: bool = False


class CostEstimate(BaseModel):
    estimated_rows_scanned: int | None = None
    estimated_result_rows: int | None = None
    estimated_runtime_seconds: float | None = None
    scan_bytes: int | None = None
    partition_pruned: bool | None = None
    join_count: int = 0
    warnings: list[str] = Field(default_factory=list)
    blocked: bool = False
    block_reason: str | None = None
    suggestions: list[str] = Field(default_factory=list)


class SqlExplanation(BaseModel):
    """Business-language rationale for the generated SQL."""

    summary: str = ""
    table_reasons: list[str] = Field(default_factory=list)    # why each table was used/joined
    filter_reasons: list[str] = Field(default_factory=list)
    aggregation_reasons: list[str] = Field(default_factory=list)
    grouping_reasons: list[str] = Field(default_factory=list)


class ClarificationOption(BaseModel):
    label: str
    value: str
    description: str | None = None


class ClarificationRequest(BaseModel):
    question: str
    options: list[ClarificationOption] = Field(default_factory=list)
    allow_free_text: bool = True


class ExecutionStats(BaseModel):
    execution_time_ms: int | None = None
    row_count: int | None = None
    column_count: int | None = None
    connector_id: str | None = None
    cache_hit: bool = False
    reused_from_library: bool = False


class ResponseAction(BaseModel):
    """Configurable API action button attached to a result."""

    action_id: str
    label: str
    icon: str | None = None
    confirm: bool = True


class BeelineResponse(BaseModel):
    """The single response schema the frontend renders adaptively."""

    kind: Literal["answer", "clarification", "preview", "blocked", "error"] = "answer"
    execution_id: str | None = None
    summary: str = ""
    confidence: ConfidenceBreakdown = Field(default_factory=ConfidenceBreakdown)
    visualization: VisualizationType = "text"
    cards: list[KpiCard] = Field(default_factory=list)
    charts: list[ChartSpec] = Field(default_factory=list)
    table: TableSpec | None = None
    insights: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    follow_up_questions: list[str] = Field(default_factory=list)
    clarification: ClarificationRequest | None = None
    sql: str | None = None
    sql_explanation: SqlExplanation | None = None
    cost_estimate: CostEstimate | None = None
    stats: ExecutionStats | None = None
    tables_used: list[str] = Field(default_factory=list)
    filters_used: list[str] = Field(default_factory=list)
    metrics_used: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    actions: list[ResponseAction] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
