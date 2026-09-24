package com.beeline.ruleequivalence.api.dto;

import jakarta.validation.constraints.NotBlank;

public record EquivalenceRequest(
        @NotBlank(message = "droolsRule must not be blank") String droolsRule,
        @NotBlank(message = "sql must not be blank") String sql
) {
}
