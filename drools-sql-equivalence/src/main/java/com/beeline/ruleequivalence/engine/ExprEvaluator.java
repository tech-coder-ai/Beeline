package com.beeline.ruleequivalence.engine;

import com.beeline.ruleequivalence.ir.Expr;
import com.beeline.ruleequivalence.ir.Literal;

import java.math.BigDecimal;
import java.util.Map;

/** Evaluates an {@link Expr} tree against a concrete field assignment. */
final class ExprEvaluator {

    private ExprEvaluator() {
    }

    static boolean eval(Expr expr, Map<String, Object> env) {
        return switch (expr) {
            case Expr.BoolConst b -> b.value();
            case Expr.Not n -> !eval(n.operand(), env);
            case Expr.And a -> a.operands().stream().allMatch(op -> eval(op, env));
            case Expr.Or o -> o.operands().stream().anyMatch(op -> eval(op, env));
            case Expr.Comparison c -> evalComparison(c, env);
        };
    }

    private static boolean evalComparison(Expr.Comparison c, Map<String, Object> env) {
        Object envValue = env.get(c.field());
        Literal literal = c.value();
        int cmp;
        if (literal instanceof Literal.NumberLiteral nl) {
            cmp = ((BigDecimal) envValue).compareTo(nl.value());
        } else if (literal instanceof Literal.StringLiteral sl) {
            cmp = ((String) envValue).compareTo(sl.value());
        } else if (literal instanceof Literal.BoolLiteral bl) {
            cmp = Boolean.compare((Boolean) envValue, bl.value());
        } else {
            throw new IllegalStateException("Unknown literal type: " + literal);
        }
        return switch (c.op()) {
            case EQ -> cmp == 0;
            case NEQ -> cmp != 0;
            case LT -> cmp < 0;
            case LTE -> cmp <= 0;
            case GT -> cmp > 0;
            case GTE -> cmp >= 0;
        };
    }
}
