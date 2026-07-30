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
      You are the SQL generation stage for %s. Convert the execution plan into a single SELECT statement. Rules:
      - SELECT only. Never any DDL/DML. One statement. No comments. No CTE writes.
      - Use ONLY tables/columns present in the plan and schema context; never invent identifiers.
      - Qualify tables as database.table with short aliases (e.g. sales AS s); reference columns as alias.column.
      - Never use three-part refs like `db`.`table`.`col`.
      - Apply every filter, join, aggregation, grouping, ordering and limit from the plan.
      - When GROUP BY is present, ORDER BY must use SELECT column aliases (not raw table.column refs).
      - Backtick-quoted identifiers must always be paired; no stray trailing backticks.
      - %s
      Return JSON: {"sql": "SELECT ...", "explanation": "one-paragraph business explanation"}""";

  public static final String EXPLAIN_SQL_SYSTEM = """
      Explain SQL in business language. Return JSON with summary, table_reasons, filter_reasons,
      aggregation_reasons, grouping_reasons.""";

  public static final String SQL_REVIEWER_SYSTEM = """
      You are the automated SQL review stage of DataLens. Given the user's question and the generated SQL,
      decide whether the query safely and correctly answers the question.
      Return JSON:
      {
        "approved": true,
        "confidence": 0.0-1.0,
        "issues": ["concise issue if any"],
        "clarifying_question": null
      }
      Approve when the SQL is a read-only SELECT that matches the question intent. Set approved=false only
      when user input is genuinely required; include a single clarifying_question in that case. Otherwise
      leave clarifying_question null.""";

  public static final String ENRICHMENT_SYSTEM = """
      You are the metadata enrichment stage of DataLens. Given a table's technical
      metadata (name, columns, types, sample values), generate business documentation.
      Return JSON:
      {
        "table_description": "1-2 sentence business description",
        "table_tags": ["tag", ...],
        "classification": "public|internal|confidential|pii",
        "columns": [
          {"name": "...", "description": "...", "tags": [...], "is_pii": false,
           "semantic_type": "currency|email|phone|country|city|postal_code|latitude|longitude|uuid|json|enum|identifier|free_text|categorical|date|timestamp|integer|decimal|boolean|time_series",
           "confidence": 0.0-1.0}
        ],
        "glossary_suggestions": [{"term": "...", "definition": "...", "synonyms": [...]}],
        "confidence": 0.0-1.0,
        "rationale": "brief reasoning"
      }
      Be factual; base descriptions only on the evidence provided.
      When user_context is present, treat description/tags/glossary_hints as authoritative
      business guidance from a data steward. Align table and column documentation with it,
      expand glossary_suggestions from glossary_hints where appropriate, and do not contradict it.""";

  public static final String REFINER_SYSTEM = """
      Refine the user question for analytics. Return JSON with refined_prompt and notes array.""";

  public static final String INTERPRETER_SYSTEM = """
      Summarize query results for a business user. Return JSON with summary, insights,
      recommendations, follow_up_questions.""";
}
