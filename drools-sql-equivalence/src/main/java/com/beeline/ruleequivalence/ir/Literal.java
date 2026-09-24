package com.beeline.ruleequivalence.ir;

import java.math.BigDecimal;

/**
 * A constant value appearing on the right-hand side of a {@link Comparison}.
 * Restricting comparisons to field-vs-literal (never field-vs-field) is what
 * makes the critical-value equivalence check in the engine package exact.
 */
public sealed interface Literal permits Literal.NumberLiteral, Literal.StringLiteral, Literal.BoolLiteral {

    record NumberLiteral(BigDecimal value) implements Literal {
        @Override
        public String toString() {
            return value.stripTrailingZeros().toPlainString();
        }
    }

    record StringLiteral(String value) implements Literal {
        @Override
        public String toString() {
            return "'" + value.replace("'", "''") + "'";
        }
    }

    record BoolLiteral(boolean value) implements Literal {
        @Override
        public String toString() {
            return Boolean.toString(value);
        }
    }
}
