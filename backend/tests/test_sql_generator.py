"""Deterministic SQL builder - the graceful-degradation path when the LLM is unavailable."""
from app.pipeline.stages.sql_generator import SQLGenerator
from app.pipeline.types import ExecutionPlan, PlanAggregation, PlanFilter, PlanJoin


def test_builds_simple_aggregation():
    plan = ExecutionPlan(
        tables=["sales.orders"],
        columns=["sales.orders.region"],
        aggregations=[PlanAggregation(function="sum", column="sales.orders.amount", alias="total")],
        group_by=["sales.orders.region"],
        limit=20,
    )
    sql = SQLGenerator.build_deterministic(plan)
    assert "SUM(`sales`.`orders`.`amount`) AS `total`" in sql
    assert "GROUP BY `sales`.`orders`.`region`" in sql
    assert "LIMIT 20" in sql


def test_builds_join_and_filter():
    plan = ExecutionPlan(
        tables=["sales.orders", "sales.customers"],
        columns=["sales.customers.name"],
        joins=[PlanJoin(
            left_table="sales.orders", left_column="customer_id",
            right_table="sales.customers", right_column="id",
        )],
        filters=[PlanFilter(column="sales.orders.region", operator="=", value="APAC")],
    )
    sql = SQLGenerator.build_deterministic(plan)
    assert "JOIN `sales`.`customers`" in sql
    assert "WHERE `sales`.`orders`.`region` = 'APAC'" in sql


def test_relative_date_filter_translates():
    plan = ExecutionPlan(
        tables=["sales.orders"],
        columns=["sales.orders.region"],
        filters=[PlanFilter(column="sales.orders.order_date", operator="=", value="relative:last_6_months")],
    )
    sql = SQLGenerator.build_deterministic(plan)
    assert "add_months(current_date, -6)" in sql


def test_in_operator_renders_list():
    plan = ExecutionPlan(
        tables=["sales.orders"],
        columns=["sales.orders.region"],
        filters=[PlanFilter(column="sales.orders.region", operator="in", value=["APAC", "EMEA"])],
    )
    sql = SQLGenerator.build_deterministic(plan)
    assert "IN ('APAC', 'EMEA')" in sql
