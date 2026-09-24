package com.beeline.ruleequivalence.ir;

import java.util.List;

/**
 * Common intermediate representation both the Drools LHS parser and the SQL
 * WHERE-predicate parser lower their respective ASTs into. Everything below
 * this point (normalization, equivalence checking) operates only on this IR
 * and knows nothing about Drools or SQL.
 */
public sealed interface Expr permits Expr.And, Expr.Or, Expr.Not, Expr.Comparison, Expr.BoolConst {

    record And(List<Expr> operands) implements Expr {
        public And {
            operands = List.copyOf(operands);
        }
    }

    record Or(List<Expr> operands) implements Expr {
        public Or {
            operands = List.copyOf(operands);
        }
    }

    record Not(Expr operand) implements Expr {
    }

    record Comparison(String field, Op op, Literal value) implements Expr {
        public Comparison {
            field = field.toLowerCase();
        }
    }

    record BoolConst(boolean value) implements Expr {
    }
}
