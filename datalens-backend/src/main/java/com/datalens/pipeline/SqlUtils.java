package com.datalens.pipeline;

import com.datalens.core.exception.ValidationFailed;
import com.datalens.pipeline.ExecutionPlanModel.PlanAggregation;
import com.datalens.pipeline.ExecutionPlanModel.PlanFilter;
import com.datalens.pipeline.ExecutionPlanModel.PlanJoin;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import net.sf.jsqlparser.parser.CCJSqlParserUtil;
import net.sf.jsqlparser.statement.select.Limit;
import net.sf.jsqlparser.statement.select.PlainSelect;
import net.sf.jsqlparser.statement.select.Select;

public final class SqlUtils {
  private static final Pattern TRIPLE = Pattern.compile("`([^`]+)`\\.`([^`]+)`\\.`([^`]+)`");
  private static final Pattern FROM_JOIN =
      Pattern.compile("(?i)(\\b(?:FROM|JOIN)\\s+)`([^`]+)`\\.`([^`]+)`(\\s|$)");
  private static final Pattern SQL_FENCE =
      Pattern.compile("```(?:sql)?\\s*(.+?)\\s*```", Pattern.DOTALL | Pattern.CASE_INSENSITIVE);

  private SqlUtils() {}

  public static String sanitizeSql(String sql, String dialect) {
    if (sql == null) return "";
    String text = sql.strip().replaceAll(";\\s*$", "").strip();
    if (text.isBlank()) return text;
    text = stripTrailingStrayBackticks(text);
    if ("hive".equalsIgnoreCase(dialect)) text = normalizeHiveIdentifiers(text);
    if (canParse(text)) return text;
    String repaired = text;
    while (repaired.endsWith("`") && !canParse(repaired)) repaired = repaired.substring(0, repaired.length() - 1).strip();
    return canParse(repaired) ? repaired : text;
  }

  public static String normalizeHiveIdentifiers(String sql) {
    java.util.Map<String, String> aliasMap = new java.util.LinkedHashMap<>();
    java.util.Set<String> used = new java.util.HashSet<>();
    Matcher triple = TRIPLE.matcher(sql);
    while (triple.find()) aliasFor(aliasMap, used, triple.group(1), triple.group(2));
    Matcher fj = FROM_JOIN.matcher(sql);
    while (fj.find()) aliasFor(aliasMap, used, fj.group(2), fj.group(3));
    if (aliasMap.isEmpty()) return sql;
    sql =
        FROM_JOIN.matcher(sql)
            .replaceAll(
                mr -> {
                  String alias = aliasFor(aliasMap, used, mr.group(2), mr.group(3));
                  return mr.group(1) + "`" + mr.group(2) + "`.`" + mr.group(3) + "` " + alias + mr.group(4);
                });
    sql =
        TRIPLE.matcher(sql)
            .replaceAll(
                mr -> {
                  String alias = aliasFor(aliasMap, used, mr.group(1), mr.group(2));
                  return "`" + alias + "`.`" + mr.group(3) + "`";
                });
    return sql;
  }

  private static String aliasFor(
      java.util.Map<String, String> aliasMap, java.util.Set<String> used, String db, String table) {
    String key = db.toLowerCase() + "|" + table.toLowerCase();
    return aliasMap.computeIfAbsent(
        key,
        k -> {
          String[] parts = table.split("_");
          String base =
              parts.length > 0 && !parts[0].isBlank()
                  ? String.valueOf(parts[0].charAt(0))
                  : table.substring(0, Math.min(2, table.length()));
          String candidate = base.toLowerCase();
          int n = 1;
          while (used.contains(candidate)) candidate = base.toLowerCase() + n++;
          used.add(candidate);
          return candidate;
        });
  }

  private static String stripTrailingStrayBackticks(String sql) {
    String text = sql.stripTrailing();
    while (text.endsWith("`") && count(text, '`') % 2 == 1) text = text.substring(0, text.length() - 1).stripTrailing();
    return text;
  }

  private static int count(String s, char c) {
    int n = 0;
    for (int i = 0; i < s.length(); i++) if (s.charAt(i) == c) n++;
    return n;
  }

  private static boolean canParse(String sql) {
    try {
      CCJSqlParserUtil.parse(sql);
      return true;
    } catch (Exception e) {
      return false;
    }
  }

  public static String compactConnectorError(String message) {
    if (message == null) return "";
    message = message.replaceFirst("(?i)^Hive execution failed after \\d+ attempts:\\s*", "");
    if (message.length() <= 700) return message;
    return message.substring(0, 700).strip() + "… (see Admin → Logs for full trace)";
  }

  public static String injectLimit(String sql, int limit) {
    try {
      var stmt = CCJSqlParserUtil.parse(sql);
      if (stmt instanceof Select select && select.getPlainSelect() != null) {
        PlainSelect ps = select.getPlainSelect();
        if (ps.getLimit() == null) {
          Limit lim = new Limit();
          lim.setRowCount(new net.sf.jsqlparser.expression.LongValue(limit));
          ps.setLimit(lim);
          return select.toString();
        }
      }
    } catch (Exception ignored) {
    }
    return sql;
  }

  /** Normalize table refs from JSqlParser/sqlglot for catalog lookup (db.table). */
  public static String normalizeTableRef(String ref) {
    if (ref == null) return "";
    String t = ref.replace("`", "").replace("\"", "").trim().toLowerCase(Locale.ROOT);
    String[] parts = t.split("\\.");
    if (parts.length >= 3) {
      return parts[parts.length - 2] + "." + parts[parts.length - 1];
    }
    return t;
  }

  /** Extract SQL from LLM JSON map or markdown/sql prose. */
  @SuppressWarnings("unchecked")
  public static String extractSqlFromLlm(Map<String, Object> parsed, String rawText) {
    if (parsed != null && parsed.get("sql") != null) {
      String sql = String.valueOf(parsed.get("sql")).strip();
      if (!sql.isBlank()) return sql;
    }
    if (rawText == null) return "";
    String text = rawText.strip();
    Matcher fence = SQL_FENCE.matcher(text);
    if (fence.find()) return fence.group(1).strip();
    if (text.regionMatches(true, 0, "SELECT", 0, 6)) {
      int semi = text.indexOf(';');
      return semi >= 0 ? text.substring(0, semi).strip() : text;
    }
    return "";
  }

  public static String buildDeterministic(ExecutionPlanModel plan) {
    if (plan == null || plan.getTables().isEmpty()) {
      throw new ValidationFailed(
          "I couldn't map your question to any known tables. Try mentioning the dataset explicitly.");
    }
    List<String> selectParts = new ArrayList<>();
    for (String col : plan.getColumns()) {
      selectParts.add(colRef(col) + " AS `" + col.split("\\.")[col.split("\\.").length - 1] + "`");
    }
    for (PlanAggregation agg : plan.getAggregations()) {
      String fn = agg.getFunction() != null ? agg.getFunction().toUpperCase(Locale.ROOT) : "SUM";
      String target = "*".equals(agg.getColumn()) ? "*" : colRef(agg.getColumn());
      String alias =
          agg.getAlias() != null && !agg.getAlias().isBlank()
              ? agg.getAlias()
              : fn + "_" + (agg.getColumn() != null ? agg.getColumn().split("\\.")[agg.getColumn().split("\\.").length - 1] : "all");
      selectParts.add(fn + "(" + target + ") AS `" + alias + "`");
    }
    if (selectParts.isEmpty()) selectParts.add("*");

    String base = plan.getTables().get(0);
    StringBuilder sql = new StringBuilder("SELECT ").append(String.join(", ", selectParts));
    sql.append("\nFROM ").append(qident(base));

    java.util.Set<String> joined = new java.util.HashSet<>();
    joined.add(normalizeTableRef(base));
    for (PlanJoin join : plan.getJoins()) {
      String target =
          joined.contains(normalizeTableRef(join.getRightTable()))
              ? join.getLeftTable()
              : join.getRightTable();
      if (joined.contains(normalizeTableRef(target))) continue;
      joined.add(normalizeTableRef(target));
      String jt =
          switch (join.getJoinType() != null ? join.getJoinType().toLowerCase(Locale.ROOT) : "inner") {
            case "left" -> "LEFT JOIN";
            case "right" -> "RIGHT JOIN";
            case "full" -> "FULL OUTER JOIN";
            default -> "JOIN";
          };
      sql.append("\n")
          .append(jt)
          .append(" ")
          .append(qident(target))
          .append(" ON ")
          .append(qident(join.getLeftTable()))
          .append(".`")
          .append(join.getLeftColumn())
          .append("` = ")
          .append(qident(join.getRightTable()))
          .append(".`")
          .append(join.getRightColumn())
          .append("`");
    }

    List<String> conditions = new ArrayList<>();
    for (PlanFilter f : plan.getFilters()) {
      conditions.add(colRef(f.getColumn()) + " " + f.getOperator() + " " + literal(f.getValue()));
    }
    if (!conditions.isEmpty()) {
      sql.append("\nWHERE ").append(String.join("\n  AND ", conditions));
    }
    if (!plan.getGroupBy().isEmpty()) {
      sql.append("\nGROUP BY ").append(String.join(", ", plan.getGroupBy().stream().map(SqlUtils::colRef).toList()));
    }
    if (plan.getLimit() != null) sql.append("\nLIMIT ").append(plan.getLimit());
    return sql.toString();
  }

  private static String qident(String qualified) {
    return String.join(".", java.util.Arrays.stream(qualified.split("\\.")).map(p -> "`" + p + "`").toList());
  }

  private static String colRef(String qualified) {
    if (qualified == null) return "`*`";
    return qualified.contains(".") ? qident(qualified) : "`" + qualified + "`";
  }

  private static String literal(Object value) {
    if (value == null) return "NULL";
    if (value instanceof Number) return String.valueOf(value);
    if (value instanceof Boolean b) return b ? "TRUE" : "FALSE";
    return "'" + String.valueOf(value).replace("'", "''") + "'";
  }
}
