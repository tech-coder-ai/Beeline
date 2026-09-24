package com.beeline.ruleequivalence.parser;

import com.beeline.ruleequivalence.ir.Expr;

import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Lowers the WHERE predicate of a SQL / Spark SQL statement into the common
 * {@link Expr} IR. If no {@code SELECT ... WHERE} shape is found, the whole
 * input is treated as a bare boolean predicate (so callers can pass just
 * {@code age >= 18 AND status = 'ACTIVE'} directly).
 *
 * Scope: this compares filter-predicate logic only -- the boolean condition
 * under WHERE. It does not model JOINs, aggregates, GROUP BY/HAVING,
 * subqueries, or CASE-derived output columns; those change what a query
 * *produces*, not just which rows a single predicate keeps, and would need
 * a real relational-algebra IR (e.g. built on Calcite or Spark's Catalyst
 * analyzer) rather than this predicate-logic fragment.
 */
public final class SqlWherePredicateParser {

    private static final Pattern WHERE = Pattern.compile("\\bwhere\\b", Pattern.CASE_INSENSITIVE);
    private static final Pattern TERMINATOR = Pattern.compile(
            "\\b(group\\s+by|order\\s+by|having|limit|qualify|window|fetch)\\b", Pattern.CASE_INSENSITIVE);

    private SqlWherePredicateParser() {
    }

    public static Expr parsePredicate(String sql) {
        if (sql == null || sql.isBlank()) {
            throw new IllegalArgumentException("SQL input is empty");
        }
        String trimmed = sql.trim();
        if (trimmed.endsWith(";")) {
            trimmed = trimmed.substring(0, trimmed.length() - 1).trim();
        }

        Matcher whereM = WHERE.matcher(trimmed);
        String predicateText;
        if (whereM.find()) {
            int start = whereM.end();
            Matcher termM = TERMINATOR.matcher(trimmed);
            int end = termM.find(start) ? termM.start() : trimmed.length();
            predicateText = trimmed.substring(start, end).trim();
        } else {
            predicateText = trimmed;
        }
        return BooleanExpressionParser.parse(predicateText);
    }
}
