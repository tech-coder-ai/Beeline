package com.datalens.pipeline;

import com.datalens.core.exception.ValidationFailed;
import com.datalens.pipeline.ExecutionPlanModel.PlanAggregation;
import com.datalens.pipeline.ExecutionPlanModel.PlanFilter;
import com.datalens.pipeline.ExecutionPlanModel.PlanJoin;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
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
  private static final Pattern ANY_QUOTED_IDENT = Pattern.compile("\"([A-Za-z_][A-Za-z0-9_ $]*)\"");
  private static final Pattern SELECT_STAR =
      Pattern.compile("(?is)^\\s*SELECT\\s+(?:(?:ALL|DISTINCT)\\s+)?(?:[A-Za-z_][A-Za-z0-9_]*\\.)?\\*");
  private static final Map<String, String> RELATIVE_HIVE =
      Map.of(
          "relative:last_7_days", "date_sub(current_date, 7)",
          "relative:last_30_days", "date_sub(current_date, 30)",
          "relative:last_90_days", "date_sub(current_date, 90)",
          "relative:last_month", "add_months(current_date, -1)",
          "relative:last_3_months", "add_months(current_date, -3)",
          "relative:last_6_months", "add_months(current_date, -6)",
          "relative:last_12_months", "add_months(current_date, -12)",
          "relative:last_year", "add_months(current_date, -12)",
          "relative:ytd", "trunc(current_date, 'YYYY')");
  private static final Map<String, String> AGG_SQL =
      Map.of(
          "sum", "SUM({c})",
          "avg", "AVG({c})",
          "count", "COUNT({c})",
          "count_distinct", "COUNT(DISTINCT {c})",
          "min", "MIN({c})",
          "max", "MAX({c})",
          "median", "PERCENTILE_APPROX({c}, 0.5)",
          "stddev", "STDDEV({c})",
          "variance", "VARIANCE({c})");

  private SqlUtils() {}

  public static String sanitizeSql(String sql, String dialect) {
    if (sql == null) return "";
    String text = sql.strip();
    Matcher fence = SQL_FENCE.matcher(text);
    if (fence.find()) text = fence.group(1).strip();
    text = text.replaceAll(";\\s*$", "").strip();
    if (text.isBlank()) return text;
    text = normalizeQuoteCharacters(text);
    text = stripTrailingStrayBackticks(text);
    if ("hive".equalsIgnoreCase(dialect)) {
      text = doubleQuotedIdentifiersToBackticks(text);
      text = normalizeHiveIdentifiers(text);
      text = fixHiveGroupedOrderBy(text);
    }
    if (canParse(text)) return text;
    String repaired = text;
    while (repaired.endsWith("`") && !canParse(repaired)) repaired = repaired.substring(0, repaired.length() - 1).strip();
    if (canParse(repaired)) return repaired;
    // Last resort for Hive: convert every remaining double-quoted single token to backticks.
    if ("hive".equalsIgnoreCase(dialect)) {
      String allBackticks = ANY_QUOTED_IDENT.matcher(text).replaceAll(mr -> "`" + mr.group(1) + "`");
      if (canParse(allBackticks)) return allBackticks;
    }
    return text;
  }

  /** Replace typographic quotes the LLM sometimes emits with plain ASCII quotes. */
  private static String normalizeQuoteCharacters(String sql) {
    return sql.replace('\u201c', '"')
        .replace('\u201d', '"')
        .replace('\u2018', '\'')
        .replace('\u2019', '\'')
        .replace('\u00b4', '\'');
  }

  /**
   * Hive quotes identifiers with backticks, not double quotes. Convert the unambiguous identifier
   * positions - {@code AS "alias"}, {@code FROM/JOIN "db"."table"}, and dotted refs {@code "a"."b"} -
   * while leaving double-quoted comparison values (string literals) untouched.
   */
  public static String doubleQuotedIdentifiersToBackticks(String sql) {
    if (sql == null || sql.indexOf('"') < 0) return sql;
    String out = sql;
    // AS "alias"  ->  AS `alias`
    out =
        Pattern.compile("(?i)(\\bAS\\s+)\"([A-Za-z_][A-Za-z0-9_ $]*)\"")
            .matcher(out)
            .replaceAll(mr -> mr.group(1) + "`" + mr.group(2) + "`");
    // FROM "db"."table" / JOIN "db"."table" / FROM "table"
    out =
        Pattern.compile("(?i)(\\b(?:FROM|JOIN)\\s+)\"([A-Za-z_][A-Za-z0-9_$]*)\"(\\.\"([A-Za-z_][A-Za-z0-9_$]*)\")?")
            .matcher(out)
            .replaceAll(
                mr ->
                    mr.group(4) != null
                        ? mr.group(1) + "`" + mr.group(2) + "`.`" + mr.group(4) + "`"
                        : mr.group(1) + "`" + mr.group(2) + "`");
    // dotted references anywhere: "a"."b" or "a".b or a."b"
    out =
        Pattern.compile("\"([A-Za-z_][A-Za-z0-9_$]*)\"(?=\\.)")
            .matcher(out)
            .replaceAll(mr -> "`" + mr.group(1) + "`");
    out =
        Pattern.compile("(?<=\\.)\"([A-Za-z_][A-Za-z0-9_$]*)\"")
            .matcher(out)
            .replaceAll(mr -> "`" + mr.group(1) + "`");
    // GROUP BY / ORDER BY "col"
    out =
        Pattern.compile("(?i)(\\b(?:GROUP\\s+BY|ORDER\\s+BY|ON)\\s+)\"([A-Za-z_][A-Za-z0-9_$]*)\"")
            .matcher(out)
            .replaceAll(mr -> mr.group(1) + "`" + mr.group(2) + "`");
    return out;
  }

  private static final Pattern FROM_JOIN_WITH_ALIAS =
      Pattern.compile(
          "(?i)\\b(?:FROM|JOIN)\\s+`([^`]+)`\\.`([^`]+)`\\s+(?:AS\\s+)?`?([A-Za-z_][A-Za-z0-9_]*)`?");
  private static final Set<String> SQL_KEYWORDS =
      Set.of(
          "WHERE", "JOIN", "ON", "GROUP", "ORDER", "LIMIT", "LEFT", "RIGHT", "INNER", "FULL",
          "CROSS", "UNION", "HAVING", "AND", "OR", "LATERAL", "SORT", "CLUSTER", "DISTRIBUTE",
          "AS", "SELECT", "SEMI", "OUTER");

  /**
   * Hive rejects {@code `db`.`table`.`col`} references. When the SQL contains them, ensure each
   * table has an alias (reusing any alias already written) and rewrite three-part refs to
   * {@code alias.`col`}. SQL without three-part refs is returned untouched.
   */
  public static String normalizeHiveIdentifiers(String sql) {
    if (!TRIPLE.matcher(sql).find()) return sql;
    java.util.Map<String, String> aliasMap = new java.util.LinkedHashMap<>();
    java.util.Set<String> used = new java.util.HashSet<>();

    Matcher existing = FROM_JOIN_WITH_ALIAS.matcher(sql);
    while (existing.find()) {
      String alias = existing.group(3);
      if (alias != null && !SQL_KEYWORDS.contains(alias.toUpperCase(Locale.ROOT))) {
        aliasMap.put(existing.group(1).toLowerCase() + "|" + existing.group(2).toLowerCase(), alias);
        used.add(alias.toLowerCase(Locale.ROOT));
      }
    }

    Set<String> hadAlias = new java.util.HashSet<>(aliasMap.keySet());
    Matcher triple = TRIPLE.matcher(sql);
    while (triple.find()) aliasFor(aliasMap, used, triple.group(1), triple.group(2));

    sql =
        FROM_JOIN.matcher(sql)
            .replaceAll(
                mr -> {
                  String key = mr.group(2).toLowerCase() + "|" + mr.group(3).toLowerCase();
                  if (hadAlias.contains(key)) return Matcher.quoteReplacement(mr.group(0));
                  String alias = aliasFor(aliasMap, used, mr.group(2), mr.group(3));
                  return Matcher.quoteReplacement(
                      mr.group(1) + "`" + mr.group(2) + "`.`" + mr.group(3) + "` " + alias + mr.group(4));
                });
    sql =
        TRIPLE.matcher(sql)
            .replaceAll(
                mr -> {
                  String alias = aliasFor(aliasMap, used, mr.group(1), mr.group(2));
                  return Matcher.quoteReplacement("`" + alias + "`.`" + mr.group(3) + "`");
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

  /** True when the outer query projects * (or alias.*) instead of explicit columns. */
  public static boolean isSelectStar(String sql) {
    return sql != null && SELECT_STAR.matcher(sql).find();
  }

  public static String compactConnectorError(String message) {
    if (message == null) return "";
    message = message.replaceFirst("(?i)^Hive execution failed after \\d+ attempts:\\s*", "");
    if (message.startsWith("TExecuteStatementResp")) {
      for (Pattern pattern :
          List.of(
              Pattern.compile("Error while processing statement:\\s*FAILED:\\s*([^']+)", Pattern.CASE_INSENSITIVE),
              Pattern.compile("SemanticException[^:]*:\\s*([^\\]\"]+)", Pattern.CASE_INSENSITIVE),
              Pattern.compile("ParseException[^:]*:\\s*([^\\]\"]+)", Pattern.CASE_INSENSITIVE),
              Pattern.compile("AnalysisException[^:]*:\\s*([^\\]\"]+)", Pattern.CASE_INSENSITIVE),
              Pattern.compile("Execution Error[^:]*:\\s*([^\\]']+)", Pattern.CASE_INSENSITIVE))) {
        Matcher match = pattern.matcher(message);
        if (match.find()) {
          return "Hive query failed: " + match.group(match.groupCount()).trim();
        }
      }
    }
    for (Pattern pattern :
        List.of(
            Pattern.compile("SemanticException[^:]*:\\s*([^\\]\"]+)", Pattern.CASE_INSENSITIVE),
            Pattern.compile("ParseException[^:]*:\\s*([^\\]\"]+)", Pattern.CASE_INSENSITIVE),
            Pattern.compile("Invalid table alias '[^']+'", Pattern.CASE_INSENSITIVE))) {
      Matcher match = pattern.matcher(message);
      if (match.find()) {
        String detail = match.groupCount() > 0 ? match.group(1) : match.group(0);
        return "Hive query failed: " + detail.trim();
      }
    }
    if (message.length() <= 700) return message;
    return message.substring(0, 700).strip() + "… (see Admin → Logs for full trace)";
  }

  /** Hive rejects ORDER BY table.column after GROUP BY — rewrite to SELECT aliases when possible. */
  public static String fixHiveGroupedOrderBy(String sql) {
    if (sql == null || !sql.toLowerCase(Locale.ROOT).contains("group by")) return sql;
    int groupIdx = sql.toLowerCase(Locale.ROOT).indexOf("group by");
    int orderIdx = sql.toLowerCase(Locale.ROOT).indexOf("order by", groupIdx);
    if (orderIdx < 0) return sql;
    Map<String, String> exprToAlias = new java.util.LinkedHashMap<>();
    Matcher selectMatcher = Pattern.compile("(?is)SELECT\\s+(.*?)\\s+FROM\\s").matcher(sql);
    if (!selectMatcher.find()) return sql;
    String selectList = selectMatcher.group(1);
    Matcher aliasMatcher =
        Pattern.compile("(?i)(.+?)\\s+AS\\s+`([^`]+)`").matcher(selectList);
    while (aliasMatcher.find()) {
      String expr = aliasMatcher.group(1).trim();
      String alias = aliasMatcher.group(2);
      exprToAlias.put(expr, alias);
      exprToAlias.put(expr.toLowerCase(Locale.ROOT), alias);
    }
    if (exprToAlias.isEmpty()) return sql;
    String before = sql.substring(0, orderIdx);
    String orderPart = sql.substring(orderIdx);
    for (Map.Entry<String, String> e : exprToAlias.entrySet()) {
      orderPart = orderPart.replace(e.getKey(), "`" + e.getValue() + "`");
    }
    return before + orderPart;
  }

  public static Map<String, String> relativeDateTranslations() {
    return RELATIVE_HIVE;
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
    return buildDeterministic(plan, java.util.Map.of());
  }

  public static String buildDeterministic(ExecutionPlanModel plan, java.util.Map<String, String> columnTypes) {
    if (plan == null || plan.getTables().isEmpty()) {
      throw new ValidationFailed(
          "I couldn't map your question to any known tables. Try mentioning the dataset explicitly.");
    }

    java.util.Map<String, String> tableAliases = aliasMap(plan.getTables());
    List<String> selectParts = new ArrayList<>();
    for (String col : plan.getColumns()) {
      selectParts.add(hiveColRef(col, tableAliases) + " AS `" + shortName(col) + "`");
    }
    for (PlanAggregation agg : plan.getAggregations()) {
      String fn = agg.getFunction() != null ? agg.getFunction().toLowerCase(Locale.ROOT) : "sum";
      String template = AGG_SQL.getOrDefault(fn, "SUM({c})");
      String target = "*".equals(agg.getColumn()) ? "*" : hiveColRef(agg.getColumn(), tableAliases);
      String alias =
          agg.getAlias() != null && !agg.getAlias().isBlank()
              ? agg.getAlias()
              : fn + "_" + shortName(agg.getColumn()).replace("*", "all");
      selectParts.add(template.replace("{c}", target) + " AS `" + alias + "`");
    }
    if (selectParts.isEmpty()) selectParts.add("*");

    String base = plan.getTables().get(0);
    String baseAlias = tableAliases.get(normalizeTableRef(base));
    StringBuilder sql =
        new StringBuilder("SELECT ")
            .append(String.join(", ", selectParts))
            .append("\nFROM ")
            .append(hiveTableRef(base, baseAlias));

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
          .append(hiveTableRef(target, tableAliases.get(normalizeTableRef(target))))
          .append(" ON ")
          .append(hiveColRef(join.getLeftTable() + "." + join.getLeftColumn(), tableAliases))
          .append(" = ")
          .append(hiveColRef(join.getRightTable() + "." + join.getRightColumn(), tableAliases));
    }

    List<String> conditions = new ArrayList<>();
    for (PlanFilter f : plan.getFilters()) {
      conditions.add(renderFilter(f, tableAliases, columnTypes));
    }
    if (!conditions.isEmpty()) sql.append("\nWHERE ").append(String.join("\n  AND ", conditions));

    if (!plan.getGroupBy().isEmpty()) {
      sql.append("\nGROUP BY ")
          .append(String.join(", ", plan.getGroupBy().stream().map(c -> hiveColRef(c, tableAliases)).toList()));
    }
    if (plan.getOrderBy() != null && !plan.getOrderBy().isEmpty()) {
      List<String> orderParts = new ArrayList<>();
      for (Map<String, Object> o : plan.getOrderBy()) {
        Object col = o.get("column");
        if (col == null) continue;
        String direction = String.valueOf(o.getOrDefault("direction", "desc"));
        String orderExpr = hiveColRef(String.valueOf(col), tableAliases);
        for (PlanAggregation agg : plan.getAggregations()) {
          if (agg.getAlias() != null && agg.getAlias().equalsIgnoreCase(String.valueOf(col))) {
            orderExpr = "`" + agg.getAlias() + "`";
            break;
          }
        }
        orderParts.add(orderExpr + ("desc".equalsIgnoreCase(direction) ? " DESC" : " ASC"));
      }
      if (!orderParts.isEmpty()) sql.append("\nORDER BY ").append(String.join(", ", orderParts));
    }
    if (plan.getLimit() != null) sql.append("\nLIMIT ").append(plan.getLimit());
    return normalizeHiveIdentifiers(sql.toString());
  }

  private static java.util.Map<String, String> aliasMap(List<String> tables) {
    java.util.Map<String, String> out = new java.util.LinkedHashMap<>();
    java.util.Set<String> used = new java.util.HashSet<>();
    for (String table : tables) {
      String key = normalizeTableRef(table);
      String[] parts = key.split("\\.");
      String tableName = parts.length > 1 ? parts[1] : key;
      String[] tokens = tableName.split("_");
      String base =
          tokens.length > 0 && !tokens[0].isBlank()
              ? tokens[0].substring(0, Math.min(2, tokens[0].length()))
              : tableName.substring(0, Math.min(2, tableName.length()));
      String candidate = base.toLowerCase(Locale.ROOT);
      int n = 1;
      while (used.contains(candidate)) candidate = base.toLowerCase(Locale.ROOT) + n++;
      used.add(candidate);
      out.put(key, candidate);
    }
    return out;
  }

  private static String hiveTableRef(String qualified, String alias) {
    return qident(qualified) + (alias != null && !alias.isBlank() ? " " + alias : "");
  }

  private static String hiveColRef(String qualified, java.util.Map<String, String> aliases) {
    if (qualified == null || qualified.isBlank()) return "`*`";
    if (!qualified.contains(".")) return "`" + qualified + "`";
    String[] parts = qualified.split("\\.");
    if (parts.length >= 3) {
      String qual = parts[0] + "." + parts[1];
      String alias = aliases.get(normalizeTableRef(qual));
      if (alias != null) return alias + ".`" + parts[parts.length - 1] + "`";
    }
    if (parts.length == 2) {
      String alias = aliases.get(normalizeTableRef(qualified.substring(0, qualified.lastIndexOf('.'))));
      if (alias != null) return alias + ".`" + parts[1] + "`";
    }
    return qident(qualified);
  }

  private static String renderFilter(
      PlanFilter f, java.util.Map<String, String> aliases, java.util.Map<String, String> columnTypes) {
    String column = hiveColRef(f.getColumn(), aliases);
    String columnType = resolveColumnType(f.getColumn(), columnTypes);
    String compareColumn = comparisonColumnExpr(column, columnType);
    String op = f.getOperator() != null ? f.getOperator().toLowerCase(Locale.ROOT) : "=";
    Object value = f.getValue();
    if (value instanceof String s && RELATIVE_HIVE.containsKey(s)) {
      return column + " >= " + RELATIVE_HIVE.get(s);
    }
    if ("is_null".equals(op) || "is_not_null".equals(op)) {
      return compareColumn + " IS " + ("is_not_null".equals(op) ? "NOT NULL" : "NULL");
    }
    if (("in".equals(op) || "not_in".equals(op)) && value instanceof List<?> list) {
      String rendered =
          list.stream().map(v -> literal(v, columnType)).reduce((a, b) -> a + ", " + b).orElse("");
      return compareColumn + ("not_in".equals(op) ? " NOT IN (" : " IN (") + rendered + ")";
    }
    if ("between".equals(op) && value instanceof List<?> list && list.size() == 2) {
      return compareColumn
          + " BETWEEN "
          + literal(list.get(0), columnType)
          + " AND "
          + literal(list.get(1), columnType);
    }
    if ("like".equals(op)) return compareColumn + " LIKE " + literal(value, columnType);
    String sqlOp =
        switch (op) {
          case "!=", "<>" -> "<>";
          case ">" -> ">";
          case ">=" -> ">=";
          case "<" -> "<";
          case "<=" -> "<=";
          default -> "=";
        };
    return compareColumn + " " + sqlOp + " " + literal(value, columnType);
  }

  private static String resolveColumnType(String column, java.util.Map<String, String> columnTypes) {
    if (column == null || columnTypes == null || columnTypes.isEmpty()) return null;
    String key = column.toLowerCase(Locale.ROOT);
    if (columnTypes.containsKey(key)) return columnTypes.get(key);
    if (column.contains(".")) {
      String shortKey = column.substring(column.lastIndexOf('.') + 1).toLowerCase(Locale.ROOT);
      if (columnTypes.containsKey(shortKey)) return columnTypes.get(shortKey);
    }
    return null;
  }

  private static boolean isBooleanColumnType(String dataType) {
    if (dataType == null) return false;
    String dt = dataType.toLowerCase(Locale.ROOT);
    return dt.contains("boolean") || dt.equals("bool");
  }

  private static boolean isClobColumnType(String dataType) {
    if (dataType == null) return false;
    String dt = dataType.toLowerCase(Locale.ROOT);
    return dt.contains("clob")
        || dt.contains("nclob")
        || dt.contains("longvarchar")
        || dt.equals("text");
  }

  /** Hive/Spark cannot compare CLOB-like columns directly; cast to STRING first. */
  private static String comparisonColumnExpr(String column, String columnType) {
    if (isClobColumnType(columnType)) {
      return "CAST(" + column + " AS STRING)";
    }
    return column;
  }

  private static Object coerceBooleanValue(Object value) {
    if (value instanceof Boolean b) return b ? 1 : 0;
    if (value instanceof Number n) return n.intValue() != 0 ? 1 : 0;
    if (value instanceof String s) {
      String lowered = s.trim().toLowerCase(Locale.ROOT);
      if ("true".equals(lowered) || "yes".equals(lowered)) return 1;
      if ("false".equals(lowered) || "no".equals(lowered)) return 0;
    }
    return value;
  }

  private static String shortName(String qualified) {
    if (qualified == null) return "col";
    return qualified.contains(".") ? qualified.substring(qualified.lastIndexOf('.') + 1) : qualified;
  }

  private static String qident(String qualified) {
    return String.join(".", java.util.Arrays.stream(qualified.split("\\.")).map(p -> "`" + p + "`").toList());
  }

  private static String colRef(String qualified) {
    if (qualified == null) return "`*`";
    return qualified.contains(".") ? qident(qualified) : "`" + qualified + "`";
  }

  private static String literal(Object value) {
    return literal(value, null);
  }

  private static String literal(Object value, String columnType) {
    if (value == null) return "NULL";
    if (isBooleanColumnType(columnType)) {
      Object coerced = coerceBooleanValue(value);
      if (coerced instanceof Number n) return String.valueOf(n.intValue());
    }
    if (value instanceof Number) return String.valueOf(value);
    if (value instanceof Boolean b) return b ? "1" : "0";
    return "'" + String.valueOf(value).replace("'", "''") + "'";
  }
}
