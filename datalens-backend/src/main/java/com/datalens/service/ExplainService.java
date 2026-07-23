package com.datalens.service;

import com.datalens.llm.LlmPrompts;
import com.datalens.llm.LlmProviderRegistry;
import com.datalens.schema.response.SqlExplanationDto;
import java.util.List;
import java.util.Map;
import net.sf.jsqlparser.parser.CCJSqlParserUtil;
import net.sf.jsqlparser.statement.Statement;
import net.sf.jsqlparser.util.TablesNamesFinder;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class ExplainService {
  private static final Logger log = LoggerFactory.getLogger(ExplainService.class);
  private final LlmProviderRegistry llm;

  public ExplainService(LlmProviderRegistry llm) {
    this.llm = llm;
  }

  public SqlExplanationDto explain(String sql, String dialect, String question) {
    SqlExplanationDto deterministic = structural(sql);
    try {
      Map<String, Object> parsed =
          llm.completeJson(
              LlmPrompts.EXPLAIN_SQL_SYSTEM,
              (question != null ? "Original question: " + question + "\n\n" : "") + "SQL:\n" + sql);
      if (parsed.get("summary") != null) {
        SqlExplanationDto out = new SqlExplanationDto();
        out.setSummary(String.valueOf(parsed.get("summary")));
        out.setTableReasons(stringList(parsed.get("table_reasons"), deterministic.getTableReasons()));
        out.setFilterReasons(stringList(parsed.get("filter_reasons"), deterministic.getFilterReasons()));
        out.setAggregationReasons(
            stringList(parsed.get("aggregation_reasons"), deterministic.getAggregationReasons()));
        out.setGroupingReasons(stringList(parsed.get("grouping_reasons"), deterministic.getGroupingReasons()));
        return out;
      }
    } catch (Exception e) {
      log.debug("LLM explanation unavailable: {}", e.getMessage());
    }
    return deterministic;
  }

  private SqlExplanationDto structural(String sql) {
    SqlExplanationDto explanation = new SqlExplanationDto();
    explanation.setSummary("Structural breakdown of the query.");
    try {
      Statement tree = CCJSqlParserUtil.parse(sql);
      TablesNamesFinder finder = new TablesNamesFinder();
      List<String> tables = finder.getTableList(tree);
      if (!tables.isEmpty()) {
        explanation.setTableReasons(tables.stream().map(t -> "Reads from " + t).distinct().toList());
      }
    } catch (Exception e) {
      explanation.setSummary("The SQL could not be parsed for a structural explanation.");
    }
    return explanation;
  }

  @SuppressWarnings("unchecked")
  private List<String> stringList(Object value, List<String> fallback) {
    if (value instanceof List<?> l && !l.isEmpty()) return l.stream().map(String::valueOf).toList();
    return fallback;
  }
}
