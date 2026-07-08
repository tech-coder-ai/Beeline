"""Small SQL hygiene helpers shared across pipeline stages."""
from __future__ import annotations

import re

import sqlglot
from sqlglot import exp

_TRIPLE_BACKTICK = re.compile(r"`([^`]+)`\.`([^`]+)`\.`([^`]+)`")
_FROM_JOIN_TABLE = re.compile(
    r"(?P<prefix>\b(?:FROM|JOIN)\s+)`(?P<db>[^`]+)`\.`(?P<table>[^`]+)`(?P<after>(?:\s|$))",
    re.IGNORECASE,
)


def sanitize_sql(sql: str, dialect: str = "hive") -> str:
    """Fix common LLM quoting mistakes before validation/optimization."""
    text = sql.strip().rstrip(";").strip()
    if not text:
        return text

    text = _strip_trailing_stray_backticks(text)
    if dialect == "hive":
        text = normalize_hive_identifiers(text)
        text = fix_hive_grouped_order_by(text, dialect)

    if _can_parse(text, dialect):
        return text

    repaired = text
    while repaired.endswith("`") and not _can_parse(repaired, dialect):
        repaired = repaired[:-1].rstrip()
    return repaired if _can_parse(repaired, dialect) else text


def normalize_hive_identifiers(sql: str) -> str:
    """Rewrite `db`.`table`.`col` to alias form - Hive rejects 3-part backtick refs."""
    alias_map: dict[tuple[str, str], str] = {}
    used: set[str] = set()

    def alias_for(db: str, table: str) -> str:
        key = (db.lower(), table.lower())
        if key not in alias_map:
            parts = [p for p in table.split("_") if p]
            base = "".join(p[0] for p in parts) if parts else table[:2]
            candidate = base.lower() or "t"
            n = 1
            while candidate in used:
                candidate = f"{base.lower()}{n}"
                n += 1
            used.add(candidate)
            alias_map[key] = candidate
        return alias_map[key]

    for match in _TRIPLE_BACKTICK.finditer(sql):
        alias_for(match.group(1), match.group(2))
    for match in _FROM_JOIN_TABLE.finditer(sql):
        alias_for(match.group("db"), match.group("table"))

    if not alias_map:
        return sql

    def add_table_alias(match: re.Match[str]) -> str:
        db, table = match.group("db"), match.group("table")
        alias = alias_for(db, table)
        after = match.group("after")
        return f"{match.group('prefix')}`{db}`.`{table}` {alias}{after}"

    sql = _FROM_JOIN_TABLE.sub(add_table_alias, sql)

    def replace_triple(match: re.Match[str]) -> str:
        db, table, col = match.group(1), match.group(2), match.group(3)
        alias = alias_for(db, table)
        return f"`{alias}`.`{col}`"

    return _TRIPLE_BACKTICK.sub(replace_triple, sql)


def fix_hive_grouped_order_by(sql: str, dialect: str = "hive") -> str:
    """Hive rejects ORDER BY table.column after GROUP BY — use the SELECT alias instead."""
    if dialect != "hive":
        return sql
    try:
        tree = sqlglot.parse_one(sql, read=dialect)
    except Exception:  # noqa: BLE001
        return sql
    if not isinstance(tree, exp.Select):
        return sql
    group = tree.args.get("group")
    order = tree.args.get("order")
    if not group or not order:
        return sql

    expr_to_alias: dict[str, str] = {}
    for sel in tree.expressions:
        if isinstance(sel, exp.Alias):
            key = sel.this.sql(dialect=dialect)
            expr_to_alias[key] = sel.alias
            expr_to_alias[key.lower()] = sel.alias

    new_orders: list[exp.Ordered] = []
    changed = False
    for ordered in order.expressions:
        order_sql = ordered.this.sql(dialect=dialect)
        alias = expr_to_alias.get(order_sql) or expr_to_alias.get(order_sql.lower())
        if alias:
            new_orders.append(
                exp.Ordered(
                    this=exp.to_identifier(alias),
                    desc=ordered.args.get("desc"),
                    nulls_first=ordered.args.get("nulls_first"),
                )
            )
            changed = True
        else:
            new_orders.append(ordered)

    if not changed:
        return sql
    tree.set("order", exp.Order(expressions=new_orders))
    try:
        return tree.sql(dialect=dialect, pretty=True)
    except Exception:  # noqa: BLE001
        return sql


def _strip_trailing_stray_backticks(sql: str) -> str:
    text = sql.rstrip()
    while text.endswith("`") and text.count("`") % 2 == 1:
        text = text[:-1].rstrip()
    return text


def compact_connector_error(message: str, limit: int = 700) -> str:
    """Return a chat-friendly Hive/connector error without full stack traces."""
    # Strip PyHive wrapper prefix from retry logic.
    message = re.sub(
        r"^Hive execution failed after \d+ attempts:\s*",
        "",
        message,
        flags=re.IGNORECASE,
    )
    if message.startswith("TExecuteStatementResp"):
        for pattern in (
            r"Error while processing statement:\s*FAILED:\s*([^']+)",
            r"SemanticException[^:]*:\s*([^\]\"]+)",
            r"ParseException[^:]*:\s*([^\]\"]+)",
            r"Execution Error[^:]*:\s*([^\]']+)",
        ):
            match = re.search(pattern, message)
            if match:
                return f"Hive query failed: {match.group(1).strip()}"
    for pattern in (
        r"SemanticException[^:]*:\s*([^\]\"]+)",
        r"ParseException[^:]*:\s*([^\]\"]+)",
        r"Invalid table alias '[^']+'",
    ):
        match = re.search(pattern, message)
        if match:
            detail = match.group(0) if match.lastindex is None else match.group(1)
            return f"Hive query failed: {detail.strip()}"
    if len(message) <= limit:
        return message
    return message[:limit].rstrip() + "… (see Admin → Logs for full trace)"


def _can_parse(sql: str, dialect: str) -> bool:
    try:
        sqlglot.parse(sql, read=dialect)
        return True
    except Exception:  # noqa: BLE001
        return False
