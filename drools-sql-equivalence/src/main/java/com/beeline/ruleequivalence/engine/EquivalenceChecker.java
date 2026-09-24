package com.beeline.ruleequivalence.engine;

import com.beeline.ruleequivalence.ir.Expr;
import com.beeline.ruleequivalence.ir.ExprNormalizer;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ThreadLocalRandom;

/**
 * Decides whether a Drools condition tree and a SQL predicate tree are
 * semantically equivalent, by evaluating both over the field assignments
 * that matter: the critical-value combinations computed by
 * {@link DomainBuilder}. See that class's javadoc for why this is exact
 * (not approximate) for the grammar {@link com.beeline.ruleequivalence.parser.BooleanExpressionParser}
 * produces, as long as the combination count stays under {@link #MAX_EXACT_COMBINATIONS}.
 */
@Component
public class EquivalenceChecker {

    private static final long MAX_EXACT_COMBINATIONS = 200_000;
    private static final int SAMPLE_SIZE = 20_000;
    private static final int MAX_COUNTEREXAMPLES = 5;

    public EquivalenceResult check(Expr droolsExpr, Expr sqlExpr) {
        String normalizedDrools = ExprNormalizer.canonicalString(droolsExpr);
        String normalizedSql = ExprNormalizer.canonicalString(sqlExpr);
        Map<String, FieldDomain> domains = DomainBuilder.build(droolsExpr, sqlExpr);

        if (domains.isEmpty()) {
            boolean l = ExprEvaluator.eval(droolsExpr, Map.of());
            boolean r = ExprEvaluator.eval(sqlExpr, Map.of());
            List<Counterexample> mismatches = l == r ? List.of() : List.of(new Counterexample(Map.of(), l, r));
            return new EquivalenceResult(l == r, EquivalenceResult.CheckMode.EXACT, 1, mismatches,
                    normalizedDrools, normalizedSql);
        }

        long totalCombinations = 1;
        boolean overflow = false;
        for (FieldDomain d : domains.values()) {
            totalCombinations *= d.candidates().size();
            if (totalCombinations > MAX_EXACT_COMBINATIONS) {
                overflow = true;
                break;
            }
        }

        List<String> fields = new ArrayList<>(domains.keySet());
        List<List<Object>> candidateLists = fields.stream().map(f -> domains.get(f).candidates()).toList();

        return overflow
                ? sampled(droolsExpr, sqlExpr, fields, candidateLists, normalizedDrools, normalizedSql)
                : exhaustive(droolsExpr, sqlExpr, fields, candidateLists, normalizedDrools, normalizedSql);
    }

    private EquivalenceResult exhaustive(Expr droolsExpr, Expr sqlExpr, List<String> fields,
                                          List<List<Object>> candidateLists,
                                          String normalizedDrools, String normalizedSql) {
        int[] indices = new int[fields.size()];
        long cases = 0;
        List<Counterexample> counterexamples = new ArrayList<>();

        boolean hasMore = true;
        while (hasMore) {
            Map<String, Object> env = buildEnv(fields, candidateLists, indices);
            cases++;
            boolean l = ExprEvaluator.eval(droolsExpr, env);
            boolean r = ExprEvaluator.eval(sqlExpr, env);
            if (l != r) {
                counterexamples.add(toCounterexample(env, l, r));
                if (counterexamples.size() >= MAX_COUNTEREXAMPLES) {
                    // We already have proof of non-equivalence; no need to keep enumerating.
                    break;
                }
            }
            hasMore = incrementIndices(indices, candidateLists);
        }

        boolean equivalent = counterexamples.isEmpty();
        return new EquivalenceResult(equivalent, EquivalenceResult.CheckMode.EXACT, cases,
                counterexamples, normalizedDrools, normalizedSql);
    }

    private EquivalenceResult sampled(Expr droolsExpr, Expr sqlExpr, List<String> fields,
                                       List<List<Object>> candidateLists,
                                       String normalizedDrools, String normalizedSql) {
        ThreadLocalRandom random = ThreadLocalRandom.current();
        List<Counterexample> counterexamples = new ArrayList<>();
        long cases = 0;
        for (int s = 0; s < SAMPLE_SIZE; s++) {
            int[] indices = new int[fields.size()];
            for (int i = 0; i < fields.size(); i++) {
                indices[i] = random.nextInt(candidateLists.get(i).size());
            }
            Map<String, Object> env = buildEnv(fields, candidateLists, indices);
            cases++;
            boolean l = ExprEvaluator.eval(droolsExpr, env);
            boolean r = ExprEvaluator.eval(sqlExpr, env);
            if (l != r) {
                counterexamples.add(toCounterexample(env, l, r));
                if (counterexamples.size() >= MAX_COUNTEREXAMPLES) {
                    break;
                }
            }
        }
        boolean equivalent = counterexamples.isEmpty();
        return new EquivalenceResult(equivalent, EquivalenceResult.CheckMode.SAMPLED, cases,
                counterexamples, normalizedDrools, normalizedSql);
    }

    /** Advances a mixed-radix counter; returns false once every combination has been visited. */
    private static boolean incrementIndices(int[] indices, List<List<Object>> candidateLists) {
        for (int i = indices.length - 1; i >= 0; i--) {
            indices[i]++;
            if (indices[i] < candidateLists.get(i).size()) {
                return true;
            }
            indices[i] = 0;
        }
        return false;
    }

    private static Map<String, Object> buildEnv(List<String> fields, List<List<Object>> candidateLists, int[] indices) {
        Map<String, Object> env = new LinkedHashMap<>();
        for (int i = 0; i < fields.size(); i++) {
            env.put(fields.get(i), candidateLists.get(i).get(indices[i]));
        }
        return env;
    }

    private static Counterexample toCounterexample(Map<String, Object> env, boolean l, boolean r) {
        Map<String, String> display = new LinkedHashMap<>();
        env.forEach((k, v) -> display.put(k, String.valueOf(v)));
        return new Counterexample(display, l, r);
    }
}
