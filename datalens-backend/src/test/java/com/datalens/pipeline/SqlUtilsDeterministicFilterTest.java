package com.datalens.pipeline;

import static org.assertj.core.api.Assertions.assertThat;

import com.datalens.pipeline.ExecutionPlanModel.PlanFilter;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

/**
 * The deterministic SQL builder is the fallback path used when the LLM is unavailable or returns
 * empty SQL - it must apply the same case-insensitivity and NULL-or-empty-string conventions as
 * the LLM prompts (LlmPrompts.SQL_GENERATOR_SYSTEM) so behavior doesn't depend on which path
 * generated the query.
 */
class SqlUtilsDeterministicFilterTest {

  private static ExecutionPlanModel planWithFilter(PlanFilter filter) {
    ExecutionPlanModel plan = new ExecutionPlanModel();
    plan.setTables(List.of("analytics.customers"));
    plan.setColumns(List.of("analytics.customers.customer_id"));
    plan.setFilters(List.of(filter));
    return plan;
  }

  private static PlanFilter filter(String column, String operator, Object value) {
    PlanFilter f = new PlanFilter();
    f.setColumn(column);
    f.setOperator(operator);
    f.setValue(value);
    return f;
  }

  @Test
  void stringEqualityIsCaseInsensitive() {
    String sql =
        SqlUtils.buildDeterministic(
            planWithFilter(filter("analytics.customers.status", "=", "Active")));
    assertThat(sql).contains("UPPER(cu.`status`) = UPPER('Active')");
  }

  @Test
  void numericEqualityIsNotWrappedInUpper() {
    String sql =
        SqlUtils.buildDeterministic(planWithFilter(filter("analytics.customers.age", "=", 30)));
    assertThat(sql).contains("cu.`age` = 30").doesNotContain("UPPER");
  }

  @Test
  void inListOfStringsIsCaseInsensitive() {
    String sql =
        SqlUtils.buildDeterministic(
            planWithFilter(filter("analytics.customers.status", "in", List.of("Active", "Pending"))));
    assertThat(sql).contains("UPPER(cu.`status`) IN (UPPER('Active'), UPPER('Pending'))");
  }

  @Test
  void likeIsCaseInsensitive() {
    String sql =
        SqlUtils.buildDeterministic(
            planWithFilter(filter("analytics.customers.name", "like", "%smith%")));
    assertThat(sql).contains("UPPER(cu.`name`) LIKE UPPER('%smith%')");
  }

  @Test
  void isNullOnTextColumnAlsoMatchesEmptyString() {
    String sql =
        SqlUtils.buildDeterministic(
            planWithFilter(filter("analytics.customers.email", "is_null", null)),
            Map.of("email", "varchar"));
    assertThat(sql).contains("(cu.`email` IS NULL OR TRIM(cu.`email`) = '')");
  }

  @Test
  void isNotNullOnTextColumnExcludesEmptyStringToo() {
    String sql =
        SqlUtils.buildDeterministic(
            planWithFilter(filter("analytics.customers.email", "is_not_null", null)),
            Map.of("email", "varchar"));
    assertThat(sql).contains("(cu.`email` IS NOT NULL AND TRIM(cu.`email`) <> '')");
  }

  @Test
  void isNullOnUnknownColumnTypeStaysPlainNullCheck() {
    String sql =
        SqlUtils.buildDeterministic(
            planWithFilter(filter("analytics.customers.signup_count", "is_null", null)));
    assertThat(sql).contains("cu.`signup_count` IS NULL").doesNotContain("TRIM");
  }
}
