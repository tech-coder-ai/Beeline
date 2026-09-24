package com.beeline.ruleequivalence.engine;

import com.beeline.ruleequivalence.ir.Expr;
import com.beeline.ruleequivalence.ir.Literal;

import java.math.BigDecimal;
import java.math.MathContext;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;

/**
 * Computes, for every field referenced by either expression, a finite set of
 * "critical" test values: values chosen so that every region of the domain
 * the two expressions could possibly distinguish between is sampled by at
 * least one candidate. For a field only ever compared with {@code =}/{@code
 * !=}/{@code <}/{@code <=}/{@code >}/{@code >=} against literal constants
 * (which is all this grammar allows -- no field-vs-field comparisons), this
 * is a complete, not approximate, technique: checking every combination of
 * critical values is equivalent to checking every possible input.
 */
final class DomainBuilder {

    private static final BigDecimal ONE = BigDecimal.ONE;
    private static final BigDecimal TWO = new BigDecimal(2);

    private DomainBuilder() {
    }

    static Map<String, FieldDomain> build(Expr left, Expr right) {
        Map<String, List<Expr.Comparison>> byField = new LinkedHashMap<>();
        collect(left, byField);
        collect(right, byField);

        Map<String, FieldDomain> domains = new LinkedHashMap<>();
        for (Map.Entry<String, List<Expr.Comparison>> e : byField.entrySet()) {
            domains.put(e.getKey(), buildDomain(e.getKey(), e.getValue()));
        }
        return domains;
    }

    private static void collect(Expr expr, Map<String, List<Expr.Comparison>> byField) {
        switch (expr) {
            case Expr.BoolConst ignored -> {
            }
            case Expr.Not n -> collect(n.operand(), byField);
            case Expr.And a -> a.operands().forEach(op -> collect(op, byField));
            case Expr.Or o -> o.operands().forEach(op -> collect(op, byField));
            case Expr.Comparison c -> byField.computeIfAbsent(c.field(), f -> new ArrayList<>()).add(c);
        }
    }

    private static FieldDomain buildDomain(String field, List<Expr.Comparison> comparisons) {
        boolean hasNumber = comparisons.stream().anyMatch(c -> c.value() instanceof Literal.NumberLiteral);
        boolean hasString = comparisons.stream().anyMatch(c -> c.value() instanceof Literal.StringLiteral);
        boolean hasBool = comparisons.stream().anyMatch(c -> c.value() instanceof Literal.BoolLiteral);

        if (hasNumber) {
            return new FieldDomain(field, FieldDomain.Kind.NUMBER, numberCandidates(comparisons));
        }
        if (hasString) {
            return new FieldDomain(field, FieldDomain.Kind.STRING, stringCandidates(comparisons));
        }
        if (hasBool) {
            return new FieldDomain(field, FieldDomain.Kind.BOOL, List.of(Boolean.TRUE, Boolean.FALSE));
        }
        throw new IllegalStateException("Field '" + field + "' has no comparisons");
    }

    private static List<Object> numberCandidates(List<Expr.Comparison> comparisons) {
        TreeSet<BigDecimal> constants = new TreeSet<>();
        for (Expr.Comparison c : comparisons) {
            constants.add(((Literal.NumberLiteral) c.value()).value());
        }
        List<BigDecimal> sorted = new ArrayList<>(constants);
        List<Object> candidates = new ArrayList<>();
        candidates.add(sorted.get(0).subtract(ONE));
        for (int i = 0; i < sorted.size(); i++) {
            candidates.add(sorted.get(i));
            if (i < sorted.size() - 1) {
                BigDecimal mid = sorted.get(i).add(sorted.get(i + 1)).divide(TWO, MathContext.DECIMAL64);
                candidates.add(mid);
            }
        }
        candidates.add(sorted.get(sorted.size() - 1).add(ONE));
        return candidates;
    }

    private static List<Object> stringCandidates(List<Expr.Comparison> comparisons) {
        Set<String> values = new LinkedHashSet<>();
        for (Expr.Comparison c : comparisons) {
            values.add(((Literal.StringLiteral) c.value()).value());
        }
        List<Object> candidates = new ArrayList<>(values);
        candidates.add("\u0000__NONE_OF_THE_ABOVE__\u0000");
        return candidates;
    }
}
