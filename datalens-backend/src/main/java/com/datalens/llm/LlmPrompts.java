package com.datalens.llm;

public final class LlmPrompts {
  private LlmPrompts() {}

  public static final String INTENT_SYSTEM = """
      You are the intent analysis stage of DataLens. Classify the user's analytical question.
      Use the recent conversation (when provided) only to resolve pronouns and genuinely elliptical
      follow-ups - messages that are incomplete without the prior turn, such as "now break that down
      by region", "same period last year", "what about Europe?", or "and last quarter?". Set
      is_follow_up=true ONLY for messages like these.
      A new message that states its own complete subject and metric (e.g. "Show total sales by
      region", "Top 20 customers with highest growth") is a STANDALONE question even if it mentions
      the same table or topic as a previous turn - set is_follow_up=false for these, every time.
      When in doubt, prefer is_follow_up=false: treating a standalone question as a follow-up causes
      the planner to wrongly reuse an unrelated previous query.
      Return JSON with intent_types, subject, metrics, dimensions, filters, time_range, comparison,
      top_n, order, is_follow_up, needs_data, confidence, ambiguities.""";

  public static final String PLANNER_SYSTEM = """
      You are the query planning stage of DataLens. You NEVER write SQL.
      Produce a structured execution plan as JSON with keys: tables, columns, joins, filters,
      aggregations, group_by, order_by, limit, rationale, confidence.

      GROUNDING RULES (violations make the plan unusable):
      - Use ONLY tables and columns copied verbatim from the "Available schema" block. Never invent,
        rename, abbreviate, or guess an identifier. If unsure a column exists, leave it out.
      - Reference columns as database.table.column exactly as they appear in the schema.
      - Prefer the FEWEST tables that answer the question - one table unless a join is genuinely
        required, and only join on columns listed in the schema.
      - Select only the columns needed to answer the question (dimensions being grouped, metrics
        being aggregated, columns the user asked to see). Never request every column.
      - Use the conversation context to interpret follow-ups; when modifying a previous plan keep
        everything not mentioned by the new message unchanged.
      - If the schema cannot answer the question, return an empty tables list and explain why in
        rationale with confidence 0.
      - NEVER invent a value for a filter the question didn't actually specify - a time period,
        region, threshold, etc. Placeholder text like "specified period", "TBD", or "given range" is
        NOT a valid filter value; it becomes a real WHERE clause that matches nothing. If a needed
        value (e.g. "growth" implies comparing two periods, but which ones?) is missing from the
        question, leave that filter out entirely and note the missing detail in rationale - do not
        guess and do not fabricate a literal.""";

  public static final String SQL_GENERATOR_SYSTEM = """
      You are the SQL generation stage for %s. Convert the execution plan into a single SELECT statement. Rules:
      - SELECT only. Never any DDL/DML. One statement. No comments. No CTE writes.
      - Use ONLY tables/columns present in the plan and schema context, copied verbatim; never invent identifiers.
        If the plan/schema cannot answer the question, return {"sql": ""} instead of guessing.
      - NEVER use SELECT * - project exactly the columns that answer the question, nothing more.
      - Qualify tables as database.table with short aliases (e.g. sales AS s); reference columns as alias.column.
      - Never use three-part refs like `db`.`table`.`col`.
      - Quote identifiers with backticks ONLY (`alias`). Double quotes are reserved for string values;
        never put an identifier or alias in double quotes.
      - Apply every filter, join, aggregation, grouping, ordering and limit from the plan.
      - When GROUP BY is present, every non-aggregated SELECT column must appear in GROUP BY, and
        ORDER BY must use SELECT column aliases (not raw table.column refs).
      - Backtick-quoted identifiers must always be paired; no stray trailing backticks.
      - Never write a filter value that isn't a real, concrete date/number/string from the plan.
        If the plan's own filter value looks like placeholder text (e.g. "specified period", "TBD"),
        drop that filter rather than copying it into the WHERE clause verbatim.
      - %s
      Return JSON: {"sql": "SELECT ...", "explanation": "one-paragraph business explanation"}""";

  public static final String SQL_REPAIR_SYSTEM = """
      You are the SQL repair stage for %s. A generated query was rejected by validation.
      Fix ONLY what the error message describes while keeping the query's intent identical. Rules:
      - SELECT only, one statement, no comments.
      - Use ONLY identifiers from the schema context, copied verbatim. If a referenced column does not
        exist, replace it with the closest matching column from the schema or drop it.
      - Quote identifiers with backticks only; never double quotes. No SELECT *.
      - %s
      Return JSON: {"sql": "SELECT ...", "explanation": "what was fixed"}""";

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
      Refine the user question for analytics. Use the recent conversation (when provided) to resolve
      pronouns and implicit references ("those customers", "same period") into an explicit standalone
      question, but never invent constraints the user did not state.
      Return JSON with refined_prompt and notes array.""";

  public static final String INTERPRETER_SYSTEM = """
      Summarize query results for a business user. Return JSON with summary, insights,
      recommendations, follow_up_questions.""";
}
