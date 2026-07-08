"""SQL Validator guard rail tests - the platform's most critical safety layer."""
import pytest

from app.core.exceptions import GuardRailViolation
from app.pipeline.stages.validator import SQLValidator

validator = SQLValidator()

VALID_QUERIES = [
    "SELECT region, SUM(amount) AS total FROM sales.orders GROUP BY region",
    "SELECT c.name, o.amount FROM sales.customers c JOIN sales.orders o ON c.id = o.customer_id",
    "SELECT COUNT(DISTINCT customer_id) FROM sales.orders WHERE order_date >= '2024-01-01'",
]

BLOCKED_QUERIES = [
    "DROP TABLE sales.orders",
    "DELETE FROM sales.orders WHERE id = 1",
    "UPDATE sales.orders SET amount = 0",
    "INSERT INTO sales.orders VALUES (1, 2, 3)",
    "CREATE TABLE evil (id INT)",
    "ALTER TABLE sales.orders ADD COLUMN x INT",
    "TRUNCATE TABLE sales.orders",
    "SELECT * FROM sales.orders; DROP TABLE sales.orders",
    "SELECT 1 -- comment injection",
    "SELECT 1 /* block comment */",
    "MERGE INTO sales.orders USING staging ON true WHEN MATCHED THEN UPDATE SET amount = 0",
    "CALL some_procedure()",
    "SELECT * FROM sales.orders a, sales.customers b",  # cartesian join
]


@pytest.mark.parametrize("sql", VALID_QUERIES)
def test_valid_select_passes(sql):
    warnings = validator.validate(sql, "hive")
    assert isinstance(warnings, list)


@pytest.mark.parametrize("sql", BLOCKED_QUERIES)
def test_write_and_injection_patterns_blocked(sql):
    with pytest.raises(GuardRailViolation):
        validator.validate(sql, "hive")


def test_too_many_joins_blocked():
    tables = " ".join(f"JOIN t{i} ON t0.id = t{i}.id" for i in range(1, 12))
    sql = f"SELECT * FROM t0 {tables}"
    with pytest.raises(GuardRailViolation):
        validator.validate(sql, "hive")


def test_unknown_table_blocked_when_catalog_known():
    with pytest.raises(GuardRailViolation):
        validator.validate(
            "SELECT * FROM sales.orders",
            "hive",
            known_tables={"sales.customers"},
        )


def test_known_table_allowed_when_catalog_provided():
    warnings = validator.validate(
        "SELECT * FROM sales.orders",
        "hive",
        known_tables={"sales.orders"},
    )
    assert isinstance(warnings, list)
