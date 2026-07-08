"""Tests for SQL sanitization helpers."""
from app.pipeline.sql_utils import normalize_hive_identifiers, sanitize_sql
from app.pipeline.stages.validator import SQLValidator

validator = SQLValidator()


def test_sanitize_trailing_stray_backtick():
    sql = (
        "SELECT `sales`.`dim_products`.`product_name`, "
        "trunc(`sales`.`fact_sales`.`order_date`, 'MM') AS `order_month` "
        "FROM `sales`.`fact_sales` "
        "GROUP BY `sales`.`dim_products`.`product_name`, "
        "trunc(`sales`.`fact_sales`.`order_date`, 'MM')`"
    )
    fixed = sanitize_sql(sql, "hive")
    assert fixed.endswith("'MM')")
    assert not fixed.endswith("`")
    assert "`sales`.`fact_sales`." not in fixed
    validator.validate(fixed, "hive")


def test_normalize_hive_three_part_identifiers():
    sql = (
        "SELECT `sales`.`dim_products`.`product_name`, "
        "SUM(`sales`.`fact_sales`.`amount`) "
        "FROM `sales`.`fact_sales` "
        "INNER JOIN `sales`.`dim_products` "
        "ON `sales`.`fact_sales`.`product_id` = `sales`.`dim_products`.`product_id` "
        "GROUP BY `sales`.`dim_products`.`product_name`"
    )
    fixed = normalize_hive_identifiers(sql)
    assert "`sales`.`fact_sales`." not in fixed
    assert "FROM `sales`.`fact_sales` fs" in fixed or "FROM `sales`.`fact_sales` f" in fixed
    assert "JOIN `sales`.`dim_products`" in fixed
    validator.validate(fixed, "hive")


def test_trunc_expression_normalized_for_hive():
    sql = (
        "SELECT trunc(`sales`.`fact_sales`.`order_date`, 'MM') "
        "FROM `sales`.`fact_sales`"
    )
    fixed = sanitize_sql(sql, "hive")
    assert "`sales`.`fact_sales`." not in fixed
    validator.validate(fixed, "hive")


def test_fix_hive_order_by_uses_select_alias_after_group_by():
    sql = (
        "SELECT fs.region AS region, TRUNC(fs.order_date, 'MM') AS order_month, "
        "SUM(fs.amount) AS total_sales "
        "FROM sales.fact_sales AS fs "
        "GROUP BY fs.region, TRUNC(fs.order_date, 'MM') "
        "ORDER BY TRUNC(fs.order_date, 'MM') ASC"
    )
    fixed = sanitize_sql(sql, "hive")
    assert "ORDER BY order_month" in fixed or "ORDER BY\n  order_month" in fixed
    assert "ORDER BY TRUNC(fs.order_date" not in fixed
    validator.validate(fixed, "hive")
