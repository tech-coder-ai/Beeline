package com.beeline.ruleequivalence;

import com.beeline.ruleequivalence.api.dto.EquivalenceRequest;
import com.beeline.ruleequivalence.api.dto.EquivalenceResponse;
import com.beeline.ruleequivalence.engine.EquivalenceChecker;
import com.beeline.ruleequivalence.service.EquivalenceService;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class EquivalenceServiceTest {

    private final EquivalenceService service = new EquivalenceService(new EquivalenceChecker());

    @Test
    void identicalConditionsAreEquivalent() {
        String drl = """
                rule "AdultActiveUsers"
                when
                    $p : Person(age >= 18, status == "ACTIVE")
                then
                    // ...
                end
                """;
        String sql = "SELECT * FROM person WHERE age >= 18 AND status = 'ACTIVE'";

        EquivalenceResponse result = service.evaluate(new EquivalenceRequest(drl, sql));

        assertThat(result.equivalent()).isTrue();
        assertThat(result.counterexamples()).isEmpty();
    }

    @Test
    void reorderedAndRenamedButLogicallyIdenticalConditionsAreEquivalent() {
        // OR-of-ANDs vs AND-of-ORs (a De Morgan / distributive rewrite of the same logic).
        String drl = """
                when
                    eval((age >= 65 && status == "RETIRED") || (age >= 18 && status == "ACTIVE"))
                then
                end
                """;
        String sql = "SELECT * FROM person WHERE (status = 'ACTIVE' OR status = 'RETIRED') "
                + "AND ((status = 'ACTIVE' AND age >= 18) OR (status = 'RETIRED' AND age >= 65))";

        EquivalenceResponse result = service.evaluate(new EquivalenceRequest(drl, sql));

        assertThat(result.equivalent()).isTrue();
    }

    @Test
    void strictVsNonStrictBoundaryIsCaught() {
        String drl = """
                when
                    Person(age >= 18, status == "ACTIVE")
                then
                end
                """;
        String sql = "SELECT * FROM person WHERE age > 18 AND status = 'ACTIVE'";

        EquivalenceResponse result = service.evaluate(new EquivalenceRequest(drl, sql));

        assertThat(result.equivalent()).isFalse();
        assertThat(result.counterexamples()).isNotEmpty();
        assertThat(result.counterexamples().get(0).assignment()).containsEntry("age", "18");
    }

    @Test
    void differentPredicatesAreNotEquivalent() {
        String drl = """
                when
                    Account(balance > 1000 || balance < -500)
                then
                end
                """;
        String sql = "SELECT * FROM account WHERE balance > 1000";

        EquivalenceResponse result = service.evaluate(new EquivalenceRequest(drl, sql));

        assertThat(result.equivalent()).isFalse();
    }

    @Test
    void inClauseExpandsToEquivalentOrChain() {
        String drl = """
                when
                    Order(region == "EAST" || region == "WEST")
                then
                end
                """;
        String sql = "SELECT * FROM orders WHERE region IN ('EAST', 'WEST')";

        EquivalenceResponse result = service.evaluate(new EquivalenceRequest(drl, sql));

        assertThat(result.equivalent()).isTrue();
    }

    @Test
    void betweenClauseExpandsToEquivalentRange() {
        String drl = """
                when
                    Person(age >= 18, age <= 65)
                then
                end
                """;
        String sql = "SELECT * FROM person WHERE age BETWEEN 18 AND 65";

        EquivalenceResponse result = service.evaluate(new EquivalenceRequest(drl, sql));

        assertThat(result.equivalent()).isTrue();
    }
}
