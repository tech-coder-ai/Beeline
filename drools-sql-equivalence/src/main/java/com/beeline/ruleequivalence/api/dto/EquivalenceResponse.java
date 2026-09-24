package com.beeline.ruleequivalence.api.dto;

import com.beeline.ruleequivalence.engine.Counterexample;
import com.beeline.ruleequivalence.engine.EquivalenceResult;

import java.util.List;

public record EquivalenceResponse(
        boolean equivalent,
        String mode,
        long casesChecked,
        String normalizedDrools,
        String normalizedSql,
        List<Counterexample> counterexamples
) {
    public static EquivalenceResponse from(EquivalenceResult result) {
        return new EquivalenceResponse(
                result.equivalent(),
                result.mode().name(),
                result.casesChecked(),
                result.normalizedDrools(),
                result.normalizedSql(),
                result.counterexamples());
    }
}
