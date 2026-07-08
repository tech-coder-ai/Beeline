"""SQL optimizer: automatic LIMIT injection and partition-filter advisories."""
from app.pipeline.stages.optimizer import SQLOptimizer
from app.pipeline.types import PipelineContext, ResolvedTable

optimizer = SQLOptimizer()


def test_injects_default_limit_when_missing():
    sql = "SELECT region, SUM(amount) FROM sales.orders GROUP BY region"
    ctx = PipelineContext(prompt="test")
    optimized = optimizer.optimize(sql, "hive", ctx)
    assert "LIMIT" in optimized.upper()
    assert any("automatically capped" in w for w in ctx.validation_warnings)


def test_preserves_existing_limit():
    sql = "SELECT region FROM sales.orders LIMIT 50"
    ctx = PipelineContext(prompt="test")
    optimized = optimizer.optimize(sql, "hive", ctx)
    assert optimized.upper().count("LIMIT") == 1
    assert "LIMIT 50" in optimized


def test_warns_on_missing_partition_filter():
    sql = "SELECT * FROM sales.fact_sales"
    ctx = PipelineContext(prompt="test")
    ctx.resolved_tables = [
        ResolvedTable(
            id="1", database="sales", name="fact_sales", description=None,
            row_count=1_000_000, partition_columns=["order_month"], columns=[],
        )
    ]
    optimizer.optimize(sql, "hive", ctx)
    assert any("partitioned by" in w for w in ctx.validation_warnings)
