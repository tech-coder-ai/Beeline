"""Shared pipeline data structures.

The pipeline is a chain of independent stages, each reading/writing the
PipelineContext. The ExecutionPlan is the structured intermediate between
natural language and SQL - the LLM plans, deterministic code verifies.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field

IntentType = Literal[
    "aggregation", "comparison", "ranking", "filtering", "trend", "time_series",
    "top_n", "bottom_n", "grouping", "distribution", "correlation", "anomaly",
    "root_cause", "forecasting", "summarization", "window", "percentile",
    "running_total", "yoy", "mom", "qoq", "rolling_average", "cumulative_sum",
    "distinct_count", "median", "stddev", "variance", "lookup", "exploration",
    "metadata_question", "unknown",
]


class Intent(BaseModel):
    intent_types: list[str] = Field(default_factory=lambda: ["unknown"])
    subject: str = ""                       # what the question is about
    metrics: list[str] = Field(default_factory=list)
    dimensions: list[str] = Field(default_factory=list)
    filters: list[str] = Field(default_factory=list)
    time_range: str | None = None
    comparison: str | None = None           # e.g. "previous_year"
    top_n: int | None = None
    order: str | None = None                # asc | desc
    confidence: float = 0.5
    ambiguities: list[str] = Field(default_factory=list)
    is_follow_up: bool = False
    needs_data: bool = True                 # false for metadata/glossary questions


class PlanJoin(BaseModel):
    left_table: str
    left_column: str
    right_table: str
    right_column: str
    join_type: str = "inner"


class PlanFilter(BaseModel):
    column: str
    operator: str = "="
    value: Any = None
    reason: str = ""


class PlanAggregation(BaseModel):
    function: str                            # sum|avg|count|count_distinct|min|max|median|stddev
    column: str
    alias: str = ""
    reason: str = ""


class ExecutionPlan(BaseModel):
    tables: list[str] = Field(default_factory=list)          # qualified names db.table
    columns: list[str] = Field(default_factory=list)         # table.column select list (non-agg)
    joins: list[PlanJoin] = Field(default_factory=list)
    filters: list[PlanFilter] = Field(default_factory=list)
    aggregations: list[PlanAggregation] = Field(default_factory=list)
    group_by: list[str] = Field(default_factory=list)
    order_by: list[dict] = Field(default_factory=list)       # [{column, direction}]
    limit: int | None = None
    time_column: str | None = None
    time_grain: str | None = None                            # day|week|month|quarter|year
    rationale: str = ""
    confidence: float = 0.5


@dataclass
class ResolvedTable:
    id: str
    database: str
    name: str
    description: str | None
    row_count: int | None
    partition_columns: list[str]
    columns: list[dict]                     # {name, data_type, description, sample_values, is_partition}
    score: float = 0.0

    @property
    def qualified_name(self) -> str:
        return f"{self.database}.{self.name}"


@dataclass
class LibraryMatch:
    entry_id: str
    question: str
    sql: str
    similarity: float
    tables_used: list[str]


@dataclass
class PipelineContext:
    """Mutable state passed through every stage."""

    prompt: str
    session_id: str | None = None
    user_id: str = "default"
    connector_id: str | None = None

    refined_prompt: str | None = None
    refinement_notes: list[str] = field(default_factory=list)
    history: list[dict] = field(default_factory=list)         # recent turns for context
    previous_plan: ExecutionPlan | None = None
    previous_sql: str | None = None
    clarification_answer: str | None = None

    intent: Intent | None = None
    resolved_tables: list[ResolvedTable] = field(default_factory=list)
    glossary_context: list[dict] = field(default_factory=list)
    metric_context: list[dict] = field(default_factory=list)
    library_match: LibraryMatch | None = None

    plan: ExecutionPlan | None = None
    sql: str | None = None
    optimized_sql: str | None = None
    validation_warnings: list[str] = field(default_factory=list)
    cost: dict = field(default_factory=dict)

    result_columns: list[str] = field(default_factory=list)
    result_types: list[str] = field(default_factory=list)
    result_rows: list[list] = field(default_factory=list)
    row_count: int = 0
    execution_time_ms: int = 0
    truncated: bool = False
    cache_hit: bool = False

    confidence: dict = field(default_factory=lambda: {
        "business": 0.0, "metadata": 0.0, "sql": 0.0, "overall": 0.0,
    })
    warnings: list[str] = field(default_factory=list)
    llm_calls: list[dict] = field(default_factory=list)       # traceability
    execution_id: str | None = None

    def record_llm(self, purpose: str, result) -> None:
        self.llm_calls.append({
            "purpose": purpose,
            "provider": getattr(result, "provider", ""),
            "model": getattr(result, "model", ""),
            "prompt_tokens": getattr(result, "prompt_tokens", None),
            "completion_tokens": getattr(result, "completion_tokens", None),
        })

    @property
    def effective_prompt(self) -> str:
        return self.refined_prompt or self.prompt
