"""SQL Validator & Guard Rails.

Hard, non-negotiable read-only enforcement using real SQL parsing (sqlglot),
not regex alone: single statement, SELECT-only, no comments, no blocked
keywords, bounded joins/subqueries, and identifier verification against the
catalog (anti-hallucination).
"""
from __future__ import annotations

import re

import sqlglot
from sqlglot import exp

from app.core.config import get_settings
from app.core.exceptions import GuardRailViolation
from app.pipeline.sql_utils import sanitize_sql
from app.pipeline.types import PipelineContext

_COMMENT_PATTERN = re.compile(r"(--|/\*|\*/|#(?!\d))")
_SUSPICIOUS_PATTERNS = [
    re.compile(r";\s*\S"),                      # stacked statements
    re.compile(r"\bunion\b.*\bselect\b.*\bfrom\b.*\b(information_schema|sys\.)", re.I | re.S),
    re.compile(r"\binto\s+(outfile|dumpfile)\b", re.I),
]

_WRITE_EXPRESSIONS = (
    exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create, exp.Alter,
    exp.Merge, exp.TruncateTable, exp.Grant, exp.Command, exp.Set,
)


class SQLValidator:
    def validate(self, sql: str, dialect: str, ctx: PipelineContext | None = None,
                 known_tables: set[str] | None = None) -> list[str]:
        """Raises GuardRailViolation on hard failures; returns soft warnings."""
        settings = get_settings()
        warnings: list[str] = []
        stripped = sanitize_sql(sql.strip().rstrip(";").strip(), dialect)

        if not stripped:
            raise GuardRailViolation("Empty SQL statement.")
        if _COMMENT_PATTERN.search(stripped):
            raise GuardRailViolation("SQL comments are not permitted.")
        for pattern in _SUSPICIOUS_PATTERNS:
            if pattern.search(stripped):
                raise GuardRailViolation("SQL contains a prohibited pattern.")

        blocked = [k.upper() for k in settings.get("guardrails.blocked_keywords", [])]
        token_set = {t.upper() for t in re.findall(r"[A-Za-z_]+", stripped)}
        hit = token_set & set(blocked)
        if hit:
            raise GuardRailViolation(
                f"Read-only mode: statement contains prohibited keyword(s): {', '.join(sorted(hit))}."
            )

        try:
            statements = sqlglot.parse(stripped, read=dialect)
        except Exception as exc:  # noqa: BLE001
            raise GuardRailViolation(f"SQL failed to parse: {exc}") from exc

        statements = [s for s in statements if s is not None]
        if len(statements) != 1:
            raise GuardRailViolation("Exactly one SQL statement is allowed.")
        tree = statements[0]

        if isinstance(tree, _WRITE_EXPRESSIONS) or not isinstance(tree, (exp.Select, exp.Union)):
            raise GuardRailViolation("Only SELECT queries are permitted. Beeline is read-only.")
        for node in tree.walk():
            if isinstance(node, _WRITE_EXPRESSIONS):
                raise GuardRailViolation("Nested write operations are not permitted.")

        join_count = len(list(tree.find_all(exp.Join)))
        max_joins = settings.get("guardrails.max_joins", 8)
        if join_count > max_joins:
            raise GuardRailViolation(
                f"Query uses {join_count} joins; the maximum allowed is {max_joins}."
            )

        depth = self._subquery_depth(tree)
        max_depth = settings.get("guardrails.max_subquery_depth", 3)
        if depth > max_depth:
            raise GuardRailViolation(
                f"Query nests subqueries {depth} levels deep; the maximum allowed is {max_depth}."
            )

        # cartesian / cross join detection
        for join in tree.find_all(exp.Join):
            if join.kind == "CROSS" or (not join.args.get("on") and not join.args.get("using")):
                raise GuardRailViolation("Cross joins / joins without ON conditions are not permitted.")

        if any(isinstance(s, exp.Star) for s in tree.expressions):
            if settings.get("guardrails.forbid_select_star", False):
                raise GuardRailViolation("SELECT * is not permitted; choose explicit columns.")
            warnings.append("SELECT * returns all columns; consider selecting specific columns.")

        allowed_fns = {f.upper() for f in settings.get("guardrails.allowed_functions") or []}
        if allowed_fns:
            for func in tree.find_all(exp.Anonymous):
                if func.name.upper() not in allowed_fns:
                    raise GuardRailViolation(f"Function {func.name} is not on the allowlist.")

        if known_tables is not None:
            referenced = {
                ".".join(p for p in [t.db, t.name] if p).lower()
                for t in tree.find_all(exp.Table)
            }
            unknown = {t for t in referenced if t and t not in known_tables and "." in t}
            if unknown:
                raise GuardRailViolation(
                    "Query references tables missing from the catalog: " + ", ".join(sorted(unknown)),
                    detail={"unknown_tables": sorted(unknown)},
                )

        if ctx is not None and ctx.resolved_tables:
            unknown_cols = self._unknown_columns(tree, ctx)
            if unknown_cols:
                raise GuardRailViolation(
                    "Query references columns missing from the catalog: " + ", ".join(sorted(unknown_cols)),
                    detail={"unknown_columns": sorted(unknown_cols)},
                )

        if ctx is not None:
            ctx.validation_warnings.extend(warnings)
        return warnings

    @staticmethod
    def _unknown_columns(tree: exp.Expression, ctx: PipelineContext) -> set[str]:
        """Return qualified column refs that are not in resolved metadata."""
        alias_to_table: dict[str, str] = {}
        known: dict[str, set[str]] = {}
        for table in ctx.resolved_tables:
            qual = table.qualified_name.lower()
            known[qual] = {c["name"].lower() for c in table.columns}
            alias_to_table[qual] = qual

        for table in tree.find_all(exp.Table):
            qual = ".".join(p for p in [table.db, table.name] if p).lower()
            if qual in known:
                alias_to_table[qual] = qual
                if table.alias:
                    alias_to_table[str(table.alias).lower()] = qual

        output_aliases: set[str] = set()
        if isinstance(tree, exp.Select):
            for sel in tree.expressions:
                if isinstance(sel, exp.Alias):
                    output_aliases.add(sel.alias.lower())

        unknown: set[str] = set()
        for col in tree.find_all(exp.Column):
            name = (col.name or "").lower()
            if not name or name == "*" or name in output_aliases:
                continue
            table_ref = (col.table or "").lower()
            qual = alias_to_table.get(table_ref) if table_ref else None
            if not qual and len(known) == 1:
                qual = next(iter(known))
            if qual and name not in known.get(qual, set()):
                unknown.add(f"{qual}.{name}")
        return unknown

    @staticmethod
    def _subquery_depth(tree: exp.Expression) -> int:
        max_depth = 0

        def walk(node: exp.Expression, depth: int) -> None:
            nonlocal max_depth
            for child in node.iter_expressions():
                next_depth = depth + 1 if isinstance(child, (exp.Select, exp.Subquery)) else depth
                max_depth = max(max_depth, next_depth)
                walk(child, next_depth)

        walk(tree, 0)
        return max_depth
