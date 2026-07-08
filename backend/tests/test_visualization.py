"""Visualization planner: deterministic renderer selection from result shape."""
from app.pipeline.stages.visualization import VisualizationPlanner
from app.pipeline.types import Intent, PipelineContext

planner = VisualizationPlanner()


def _ctx(columns, types, rows, intent_types=None):
    ctx = PipelineContext(prompt="test")
    ctx.result_columns = columns
    ctx.result_types = types
    ctx.result_rows = rows
    ctx.row_count = len(rows)
    if intent_types:
        ctx.intent = Intent(intent_types=intent_types)
    return ctx


def test_single_row_metrics_renders_kpi():
    ctx = _ctx(["total_revenue", "total_orders"], ["decimal", "int"], [[15000.0, 42]])
    result = planner.run(ctx)
    assert result["visualization"] == "kpi"
    assert len(result["cards"]) == 2
    assert result["cards"][0].label == "Total Revenue"


def test_time_series_renders_line_chart():
    rows = [["2024-01", 100], ["2024-02", 150], ["2024-03", 90]]
    ctx = _ctx(["order_month", "revenue"], ["string", "decimal"], rows)
    result = planner.run(ctx)
    assert result["charts"]
    assert result["charts"][0].chart_type == "line"


def test_category_metric_renders_bar_chart():
    rows = [["APAC", 500], ["EMEA", 800], ["NA", 1200]]
    ctx = _ctx(["region", "revenue"], ["string", "decimal"], rows)
    result = planner.run(ctx)
    assert result["charts"]
    assert result["charts"][0].chart_type == "bar"


def test_table_always_populated_for_tabular_result():
    rows = [["APAC", 500], ["EMEA", 800]]
    ctx = _ctx(["region", "revenue"], ["string", "decimal"], rows)
    result = planner.run(ctx)
    assert result["table"] is not None
    assert len(result["table"].rows) == 2


def test_empty_result_is_text():
    ctx = _ctx(["region", "revenue"], ["string", "decimal"], [])
    result = planner.run(ctx)
    assert result["visualization"] == "text"
