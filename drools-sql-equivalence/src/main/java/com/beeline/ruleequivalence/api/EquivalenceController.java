package com.beeline.ruleequivalence.api;

import com.beeline.ruleequivalence.api.dto.EquivalenceRequest;
import com.beeline.ruleequivalence.api.dto.EquivalenceResponse;
import com.beeline.ruleequivalence.service.EquivalenceService;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class EquivalenceController {

    private final EquivalenceService service;

    public EquivalenceController(EquivalenceService service) {
        this.service = service;
    }

    @PostMapping("/api/v1/equivalence/check")
    public EquivalenceResponse check(@Valid @RequestBody EquivalenceRequest request) {
        return service.evaluate(request);
    }
}
