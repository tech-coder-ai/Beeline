package com.beeline.ruleequivalence.engine;

import java.util.Map;

/** A field assignment on which the two expressions disagree. */
public record Counterexample(Map<String, String> assignment, boolean droolsResult, boolean sqlResult) {
}
