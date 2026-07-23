package com.datalens.pipeline;

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
}
