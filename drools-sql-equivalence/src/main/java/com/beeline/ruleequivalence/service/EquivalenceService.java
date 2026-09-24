package com.beeline.ruleequivalence.service;

import com.beeline.ruleequivalence.api.dto.EquivalenceRequest;
import com.beeline.ruleequivalence.api.dto.EquivalenceResponse;
import com.beeline.ruleequivalence.engine.EquivalenceChecker;
import com.beeline.ruleequivalence.engine.EquivalenceResult;
import com.beeline.ruleequivalence.ir.Expr;
import com.beeline.ruleequivalence.parser.DroolsRuleParser;
import com.beeline.ruleequivalence.parser.SqlWherePredicateParser;
import org.springframework.stereotype.Service;

@Service
public class EquivalenceService {

    private final EquivalenceChecker checker;

    public EquivalenceService(EquivalenceChecker checker) {
        this.checker = checker;
    }

    public EquivalenceResponse evaluate(EquivalenceRequest request) {
        Expr droolsExpr = DroolsRuleParser.parseConditions(request.droolsRule());
        Expr sqlExpr = SqlWherePredicateParser.parsePredicate(request.sql());
        EquivalenceResult result = checker.check(droolsExpr, sqlExpr);
        return EquivalenceResponse.from(result);
    }
}
