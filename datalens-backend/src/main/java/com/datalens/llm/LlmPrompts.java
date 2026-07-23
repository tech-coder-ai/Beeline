package com.datalens.llm;

public final class LlmPrompts {
  private LlmPrompts() {}

  public static final String INTENT_SYSTEM = """
      You are the intent analysis stage of DataLens. Classify the user's analytical question.
      Return JSON with intent_types, subject, metrics, dimensions, filters, time_range, comparison,
      top_n, order, is_follow_up, needs_data, confidence, ambiguities.""";

  public static final String PLANNER_SYSTEM = """
      You are the query planning stage of DataLens. You NEVER write SQL.
      Produce a structured execution plan using ONLY tables/columns from the schema context.""";

  public static final String SQL_GENERATOR_SYSTEM = """
      You are the SQL generation stage for Apache Hive. Write a single SELECT statement only.""";

  public static final String EXPLAIN_SQL_SYSTEM = """
      Explain SQL in business language. Return JSON with summary, table_reasons, filter_reasons,
      aggregation_reasons, grouping_reasons.""";

  public static final String ENRICHMENT_SYSTEM = """
      Propose business metadata enrichments. Return JSON with table_description, column_descriptions,
      tags, classification, confidence, rationale.""";

  public static final String REFINER_SYSTEM = """
      Refine the user question for analytics. Return JSON with refined_prompt and notes array.""";

  public static final String INTERPRETER_SYSTEM = """
      Summarize query results for a business user. Return JSON with summary, insights,
      recommendations, follow_up_questions.""";

  public static final String SQL_REVIEWER_SYSTEM = """
      Review SQL for safety and intent match. Return JSON with approved, confidence, issues, clarification.""";
}
