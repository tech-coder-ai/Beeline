package com.datalens.pipeline;

import com.datalens.config.DataLensSettings;
import com.datalens.core.exception.GuardRailViolation;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import net.sf.jsqlparser.parser.CCJSqlParserUtil;
import net.sf.jsqlparser.statement.Statement;
import net.sf.jsqlparser.statement.select.Join;
import net.sf.jsqlparser.statement.select.PlainSelect;
import net.sf.jsqlparser.statement.select.Select;
import net.sf.jsqlparser.util.TablesNamesFinder;
import org.springframework.stereotype.Component;

@Component
public class SqlValidator {
  private static final Pattern COMMENT = Pattern.compile("(--|/\\*|\\*/|#(?!\\d))");
  private static final Pattern STACKED = Pattern.compile(";\\s*\\S");

  private final DataLensSettings settings;

  public SqlValidator(DataLensSettings settings) {
    this.settings = settings;
  }

  public List<String> validate(String sql, String dialect, PipelineContext ctx, Set<String> knownTables) {
    String stripped = SqlUtils.sanitizeSql(sql, dialect).strip();
    if (stripped.isBlank()) throw new GuardRailViolation("Empty SQL statement.");
    if (COMMENT.matcher(stripped).find()) throw new GuardRailViolation("SQL comments are not permitted.");
    if (STACKED.matcher(stripped).find()) throw new GuardRailViolation("SQL contains a prohibited pattern.");

    @SuppressWarnings("unchecked")
    List<String> blocked = (List<String>) settings.get("guardrails.blocked_keywords", List.of());
    Set<String> tokens = new HashSet<>();
    Matcher m = Pattern.compile("[A-Za-z_]+").matcher(stripped);
    while (m.find()) tokens.add(m.group().toUpperCase(Locale.ROOT));
    Set<String> hit = new HashSet<>(tokens);
    hit.retainAll(blocked.stream().map(String::toUpperCase).toList());
    if (!hit.isEmpty()) {
      throw new GuardRailViolation(
          "Read-only mode: statement contains prohibited keyword(s): " + String.join(", ", hit.stream().sorted().toList()));
    }

    Statement statement;
    try {
      statement = CCJSqlParserUtil.parse(stripped);
    } catch (Exception e) {
      throw new GuardRailViolation("SQL failed to parse: " + e.getMessage());
    }
    if (!(statement instanceof net.sf.jsqlparser.statement.select.Select select)) {
      throw new GuardRailViolation("Only SELECT queries are permitted. DataLens is read-only.");
    }

    PlainSelect plain = select.getPlainSelect();
    if (plain != null) {
      int joins = plain.getJoins() == null ? 0 : plain.getJoins().size();
      int maxJoins = ((Number) settings.get("guardrails.max_joins", 8)).intValue();
      if (joins > maxJoins) {
        throw new GuardRailViolation("Query uses " + joins + " joins; the maximum allowed is " + maxJoins + ".");
      }
      if (plain.getJoins() != null) {
        for (Join join : plain.getJoins()) {
          if (join.isCross() || (join.getOnExpression() == null && join.getUsingColumns() == null)) {
            throw new GuardRailViolation("Cross joins / joins without ON conditions are not permitted.");
          }
        }
      }
    }

    if (knownTables != null) {
      TablesNamesFinder finder = new TablesNamesFinder();
      List<String> tables = finder.getTableList(statement);
      Set<String> unknown = new HashSet<>();
      for (String t : tables) {
        String key = t.toLowerCase(Locale.ROOT);
        if (key.contains(".") && !knownTables.contains(key)) unknown.add(t);
      }
      if (!unknown.isEmpty()) {
        throw new GuardRailViolation(
            "Query references tables missing from the catalog: " + String.join(", ", unknown.stream().sorted().toList()));
      }
    }

    List<String> warnings = List.of();
    if (ctx != null) ctx.getValidationWarnings().addAll(warnings);
    return warnings;
  }
}
