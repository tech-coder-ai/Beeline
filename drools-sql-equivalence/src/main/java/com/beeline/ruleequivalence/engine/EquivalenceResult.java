package com.beeline.ruleequivalence.engine;

import java.util.List;

public record EquivalenceResult(
        boolean equivalent,
        CheckMode mode,
        long casesChecked,
        List<Counterexample> counterexamples,
        String normalizedDrools,
        String normalizedSql
) {
    public enum CheckMode {
        /** Every critical-value combination was checked -- a mathematical proof for the supported grammar. */
        EXACT,
        /** The critical-value space was too large; a large random sample was checked instead. */
        SAMPLED
    }
}
