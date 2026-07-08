"""JSON serialization helpers."""
from decimal import Decimal

from app.core.json_utils import json_safe, json_safe_tree
from app.pipeline.stages.visualization import VisualizationPlanner
from app.pipeline.types import PipelineContext


def test_json_safe_decimal():
    assert json_safe(Decimal("123.45")) == 123.45


def test_json_safe_tree_nested_decimal():
    payload = {
        "table": {"rows": [{"revenue": Decimal("99.99"), "name": "Widget"}]},
        "cards": [{"raw_value": Decimal("1000")}],
    }
    safe = json_safe_tree(payload)
    assert safe["table"]["rows"][0]["revenue"] == 99.99
    assert isinstance(safe["table"]["rows"][0]["revenue"], float)


def test_visualization_table_converts_decimal_rows():
    planner = VisualizationPlanner()
    ctx = PipelineContext(prompt="test")
    ctx.result_columns = ["product", "revenue"]
    ctx.result_types = ["string", "decimal"]
    ctx.result_rows = [["AccessLock", Decimal("636.77")], ["Widget", Decimal("1200.50")]]
    ctx.row_count = 2

    result = planner.run(ctx)
    row = result["table"].rows[0]
    assert row["revenue"] == 636.77
    assert isinstance(row["revenue"], float)
