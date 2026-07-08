"""Visualization Planner: deterministic renderer selection.

Charts are chosen by rules over the result shape - never by the LLM:
  single row of metrics -> KPI cards
  time column + metrics -> line/area chart
  low-cardinality category + metric -> bar (pie for share questions)
  two categories + metric -> heatmap
  two numerics, many rows -> scatter
  anything tabular -> AG Grid (always included alongside charts)
"""
from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.core.config import get_settings
from app.core.json_utils import json_safe
from app.pipeline.types import PipelineContext
from app.schemas.response import ChartSeries, ChartSpec, KpiCard, TableColumn, TableSpec

_DATE_TYPES = {"date", "timestamp", "datetime"}
_NUMERIC_TYPES = {"int", "integer", "bigint", "smallint", "tinyint", "float", "double",
                  "decimal", "numeric", "real", "number"}
_DATE_NAME_HINT = re.compile(r"(date|month|year|week|quarter|day|period|time)", re.I)


def _base_type(raw: str) -> str:
    return re.sub(r"[(<].*", "", (raw or "").lower()).strip()


def _is_numeric_value(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float, Decimal)):
        return True
    if isinstance(value, str):
        try:
            float(value.replace(",", ""))
            return True
        except ValueError:
            return False
    return False


def _to_number(value: Any) -> float | None:
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(",", ""))
        except ValueError:
            return None
    return None


class ColumnProfile:
    def __init__(self, name: str, declared_type: str, values: list[Any]):
        self.name = name
        base = _base_type(declared_type)
        non_null = [v for v in values if v is not None]
        self.is_temporal = (
            base in _DATE_TYPES
            or (bool(_DATE_NAME_HINT.search(name)) and not all(_is_numeric_value(v) for v in non_null[:5]))
            or any(isinstance(v, (date, datetime)) for v in non_null[:5])
            or self._looks_like_dates(non_null[:10])
        )
        self.is_numeric = not self.is_temporal and (
            base in _NUMERIC_TYPES
            or (bool(non_null) and all(_is_numeric_value(v) for v in non_null[:20]))
        )
        self.is_categorical = not self.is_temporal and not self.is_numeric
        self.distinct = len({str(v) for v in non_null})

    @staticmethod
    def _looks_like_dates(values: list[Any]) -> bool:
        pattern = re.compile(r"^\d{4}([-/]\d{1,2}){1,2}")
        strs = [v for v in values if isinstance(v, str)]
        return bool(strs) and all(pattern.match(v) for v in strs)


class VisualizationPlanner:
    def run(self, ctx: PipelineContext) -> dict:
        """Returns dict(visualization, cards, charts, table)."""
        settings = get_settings()
        columns, rows = ctx.result_columns, ctx.result_rows
        if not columns:
            return {"visualization": "text", "cards": [], "charts": [], "table": None}

        col_values = [[row[i] if i < len(row) else None for row in rows] for i in range(len(columns))]
        types = ctx.result_types or ["string"] * len(columns)
        profiles = [ColumnProfile(columns[i], types[i], col_values[i]) for i in range(len(columns))]
        table = self._table_spec(ctx, profiles)

        temporal = [i for i, p in enumerate(profiles) if p.is_temporal]
        numeric = [i for i, p in enumerate(profiles) if p.is_numeric]
        categorical = [i for i, p in enumerate(profiles) if p.is_categorical]

        cards: list[KpiCard] = []
        charts: list[ChartSpec] = []
        kpi_max = settings.get("visualization.kpi_max_values", 6)

        # single row of metrics -> KPI cards
        if len(rows) == 1 and numeric:
            for i in numeric[:kpi_max]:
                value = _to_number(rows[0][i])
                cards.append(KpiCard(
                    label=self._pretty(columns[i]),
                    value=self._format_number(value),
                    raw_value=value,
                ))
            viz = "kpi"
            return {"visualization": viz, "cards": cards, "charts": charts, "table": table}

        intent_types = set(ctx.intent.intent_types) if ctx.intent else set()

        if temporal and numeric and len(rows) > 1:
            charts.append(self._time_chart(columns, rows, temporal[0], numeric, intent_types))
        elif categorical and numeric and len(rows) > 1:
            cat = min(categorical, key=lambda i: profiles[i].distinct)
            max_pie = settings.get("visualization.max_categories_pie", 8)
            max_bar = settings.get("visualization.max_categories_bar", 30)
            wants_share = bool({"distribution", "grouping"} & intent_types) and len(numeric) == 1
            if len(categorical) >= 2 and len(numeric) >= 1 and profiles[cat].distinct <= 20:
                heat = self._heatmap(columns, rows, categorical[0], categorical[1], numeric[0])
                if heat:
                    charts.append(heat)
            if not charts and wants_share and profiles[cat].distinct <= max_pie:
                charts.append(self._pie_chart(columns, rows, cat, numeric[0]))
            if not charts and profiles[cat].distinct <= max_bar:
                charts.append(self._bar_chart(columns, rows, cat, numeric, intent_types))
        elif len(numeric) >= 2 and len(rows) > 5 and (
            "correlation" in intent_types or not categorical
        ):
            max_pts = settings.get("visualization.max_points_scatter", 5000)
            charts.append(ChartSpec(
                chart_type="scatter",
                title=f"{self._pretty(columns[numeric[1]])} vs {self._pretty(columns[numeric[0]])}",
                series=[ChartSeries(
                    name="points",
                    data=[[_to_number(r[numeric[0]]), _to_number(r[numeric[1]])] for r in rows[:max_pts]],
                )],
                x_label=self._pretty(columns[numeric[0]]),
                y_label=self._pretty(columns[numeric[1]]),
            ))

        if charts:
            viz = "mixed" if len(rows) > 1 else charts[0].chart_type
        elif len(rows) > 1:
            viz = "grid"
        elif rows:
            viz = "kpi" if cards else "grid"
        else:
            viz = "text"
        return {"visualization": viz, "cards": cards, "charts": charts, "table": table}

    # ------------------------------------------------------------ helpers
    def _time_chart(self, columns, rows, t_idx, numeric, intent_types) -> ChartSpec:
        ordered = sorted(rows, key=lambda r: str(r[t_idx]))
        chart_type = "area" if "cumulative_sum" in intent_types or "running_total" in intent_types else "line"
        return ChartSpec(
            chart_type=chart_type,
            title=f"{self._pretty(columns[numeric[0]])} over time",
            categories=[str(r[t_idx]) for r in ordered],
            series=[
                ChartSeries(name=self._pretty(columns[i]), data=[_to_number(r[i]) for r in ordered])
                for i in numeric[:4]
            ],
            x_label=self._pretty(columns[t_idx]),
        )

    def _bar_chart(self, columns, rows, cat, numeric, intent_types) -> ChartSpec:
        primary = numeric[0]
        ordered = sorted(rows, key=lambda r: -(_to_number(r[primary]) or 0))
        return ChartSpec(
            chart_type="bar",
            title=f"{self._pretty(columns[primary])} by {self._pretty(columns[cat])}",
            categories=[str(r[cat]) for r in ordered],
            series=[
                ChartSeries(name=self._pretty(columns[i]), data=[_to_number(r[i]) for r in ordered])
                for i in numeric[:3]
            ],
            x_label=self._pretty(columns[cat]),
        )

    def _pie_chart(self, columns, rows, cat, metric) -> ChartSpec:
        return ChartSpec(
            chart_type="donut",
            title=f"{self._pretty(columns[metric])} share by {self._pretty(columns[cat])}",
            series=[ChartSeries(
                name=self._pretty(columns[metric]),
                data=[{"name": str(r[cat]), "value": _to_number(r[metric])} for r in rows],
            )],
        )

    def _heatmap(self, columns, rows, cat_a, cat_b, metric) -> ChartSpec | None:
        xs = sorted({str(r[cat_a]) for r in rows})
        ys = sorted({str(r[cat_b]) for r in rows})
        if len(xs) > 30 or len(ys) > 30:
            return None
        data = [
            [xs.index(str(r[cat_a])), ys.index(str(r[cat_b])), _to_number(r[metric]) or 0]
            for r in rows
        ]
        return ChartSpec(
            chart_type="heatmap",
            title=f"{self._pretty(columns[metric])}: {self._pretty(columns[cat_a])} × {self._pretty(columns[cat_b])}",
            categories=xs,
            series=[ChartSeries(name=self._pretty(columns[cat_b]), data=data)],
            x_label=self._pretty(columns[cat_a]),
            y_label=self._pretty(columns[cat_b]),
        )

    def _table_spec(self, ctx: PipelineContext, profiles) -> TableSpec:
        columns = [
            TableColumn(
                field=p.name,
                header=self._pretty(p.name),
                data_type="date" if p.is_temporal else ("number" if p.is_numeric else "string"),
                is_metric=p.is_numeric,
            )
            for p in profiles
        ]
        rows = [
            {p.name: json_safe(row[i]) if i < len(row) else None
             for i, p in enumerate(profiles)}
            for row in ctx.result_rows
        ]
        return TableSpec(
            columns=columns, rows=rows, total_rows=ctx.row_count, truncated=ctx.truncated
        )

    @staticmethod
    def _pretty(name: str) -> str:
        return name.replace("_", " ").strip().title()

    @staticmethod
    def _format_number(value: float | None) -> str:
        if value is None:
            return "-"
        if abs(value) >= 1_000_000_000:
            return f"{value / 1_000_000_000:.2f}B"
        if abs(value) >= 1_000_000:
            return f"{value / 1_000_000:.2f}M"
        if abs(value) >= 10_000:
            return f"{value / 1_000:.1f}K"
        if value == int(value):
            return f"{int(value):,}"
        return f"{value:,.2f}"
