package com.datalens.pipeline;

import com.datalens.config.DataLensSettings;
import com.datalens.core.exception.GuardRailViolation;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import net.sf.jsqlparser.expression.Function;
import net.sf.jsqlparser.parser.CCJSqlParserUtil;
import net.sf.jsqlparser.schema.Column;
import net.sf.jsqlparser.schema.Table;
import net.sf.jsqlparser.statement.Statement;
import net.sf.jsqlparser.statement.select.AllColumns;
import net.sf.jsqlparser.statement.select.AllTableColumns;
import net.sf.jsqlparser.statement.select.FromItem;
import net.sf.jsqlparser.statement.select.Join;
import net.sf.jsqlparser.statement.select.ParenthesedSelect;
import net.sf.jsqlparser.statement.select.PlainSelect;
import net.sf.jsqlparser.statement.select.Select;
import net.sf.jsqlparser.statement.select.SelectItem;
import net.sf.jsqlparser.statement.select.SelectVisitorAdapter;
import net.sf.jsqlparser.statement.select.SetOperationList;
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
          "Read-only mode: statement contains prohibited keyword(s): "
              + String.join(", ", hit.stream().sorted().toList()));
    }

    Statement statement;
    try {
      statement = CCJSqlParserUtil.parse(stripped);
    } catch (Exception e) {
      throw new GuardRailViolation("SQL failed to parse: " + e.getMessage());
    }
    if (!(statement instanceof Select select)) {
      throw new GuardRailViolation("Only SELECT queries are permitted. DataLens is read-only.");
    }

    List<String> warnings = new ArrayList<>();
    validateSelect(select, ctx, knownTables, warnings);

    if (ctx != null) ctx.getValidationWarnings().addAll(warnings);
    return warnings;
  }

  private void validateSelect(Select select, PipelineContext ctx, Set<String> knownTables, List<String> warnings) {
    if (select.getPlainSelect() != null) {
      validatePlainSelect(select.getPlainSelect(), ctx, knownTables, warnings, 0);
      return;
    }
    if (select.getSetOperationList() != null) {
      SetOperationList setOps = select.getSetOperationList();
      for (Select body : setOps.getSelects()) {
        if (body.getPlainSelect() != null) {
          validatePlainSelect(body.getPlainSelect(), ctx, knownTables, warnings, 0);
        }
      }
    }
  }

  private void validatePlainSelect(
      PlainSelect plain, PipelineContext ctx, Set<String> knownTables, List<String> warnings, int depth) {
    int maxDepth = ((Number) settings.get("guardrails.max_subquery_depth", 3)).intValue();
    if (depth > maxDepth) {
      throw new GuardRailViolation(
          "Query nests subqueries " + depth + " levels deep; the maximum allowed is " + maxDepth + ".");
    }

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

    boolean hasStar = false;
    if (plain.getSelectItems() != null) {
      for (SelectItem<?> item : plain.getSelectItems()) {
        if (item.getExpression() instanceof AllColumns || item.getExpression() instanceof AllTableColumns) {
          hasStar = true;
        }
      }
    }
    if (hasStar) {
      if (Boolean.TRUE.equals(settings.get("guardrails.forbid_select_star", false))) {
        throw new GuardRailViolation("SELECT * is not permitted; choose explicit columns.");
      }
      warnings.add("SELECT * returns all columns; consider selecting specific columns.");
    }

    @SuppressWarnings("unchecked")
    List<String> allowedFns = (List<String>) settings.get("guardrails.allowed_functions", List.of());
    if (allowedFns != null && !allowedFns.isEmpty()) {
      Set<String> allowed = new HashSet<>();
      allowedFns.stream().map(s -> s.toUpperCase(Locale.ROOT)).forEach(allowed::add);
      plain.accept(
          new SelectVisitorAdapter<>() {
            @Override
            public void visit(Function function) {
              if (function.getName() != null && !allowed.contains(function.getName().toUpperCase(Locale.ROOT))) {
                throw new GuardRailViolation("Function " + function.getName() + " is not on the allowlist.");
              }
              super.visit(function);
            }
          });
    }

    if (knownTables != null) {
      TablesNamesFinder finder = new TablesNamesFinder();
      Select wrapper = new Select();
      wrapper.setSelectBody(plain);
      List<String> tables = finder.getTableList(wrapper);
      Set<String> unknown = new HashSet<>();
      for (String t : tables) {
        String key = SqlUtils.normalizeTableRef(t);
        if (!key.contains(".")) continue;
        if (!knownTables.contains(key)) unknown.add(t);
      }
      if (!unknown.isEmpty()) {
        throw new GuardRailViolation(
            "Query references tables missing from the catalog: "
                + String.join(", ", unknown.stream().sorted().toList()));
      }
    }

    if (ctx != null && !ctx.getResolvedTables().isEmpty()) {
      Set<String> unknownCols = unknownColumns(plain, ctx);
      if (!unknownCols.isEmpty()) {
        throw new GuardRailViolation(
            "Query references columns missing from the catalog: "
                + String.join(", ", unknownCols.stream().sorted().toList()));
      }
    }

    plain.accept(
        new SelectVisitorAdapter<>() {
          @Override
          public void visit(ParenthesedSelect subSelect) {
            if (subSelect.getSelect() != null && subSelect.getSelect().getPlainSelect() != null) {
              validatePlainSelect(subSelect.getSelect().getPlainSelect(), ctx, knownTables, warnings, depth + 1);
            }
            super.visit(subSelect);
          }
        });
  }

  private Set<String> unknownColumns(PlainSelect plain, PipelineContext ctx) {
    Map<String, Set<String>> known = new HashMap<>();
    for (ResolvedTableModel table : ctx.getResolvedTables()) {
      Set<String> cols = new HashSet<>();
      for (Map<String, Object> col : table.getColumns()) {
        if (col.get("name") != null) cols.add(String.valueOf(col.get("name")).toLowerCase(Locale.ROOT));
      }
      known.put(table.qualifiedName().toLowerCase(Locale.ROOT), cols);
    }

    Map<String, String> aliasToQual = new HashMap<>();
    registerFromItem(plain.getFromItem(), aliasToQual, known);
    if (plain.getJoins() != null) {
      for (Join join : plain.getJoins()) registerFromItem(join.getRightItem(), aliasToQual, known);
    }

    Set<String> outputAliases = new HashSet<>();
    if (plain.getSelectItems() != null) {
      for (SelectItem<?> item : plain.getSelectItems()) {
        if (item.getAlias() != null && item.getAlias().getName() != null) {
          outputAliases.add(item.getAlias().getName().toLowerCase(Locale.ROOT));
        }
      }
    }

    Set<String> unknown = new HashSet<>();
    plain.accept(
        new SelectVisitorAdapter<>() {
          @Override
          public void visit(Column column) {
            String name = column.getColumnName();
            if (name == null || name.isBlank() || "*".equals(name)) return;
            if (outputAliases.contains(name.toLowerCase(Locale.ROOT))) return;

            String tableRef =
                column.getTable() != null && column.getTable().getName() != null
                    ? column.getTable().getName().toLowerCase(Locale.ROOT)
                    : null;
            String qual = tableRef != null ? aliasToQual.get(tableRef) : null;
            if (qual == null && known.size() == 1) qual = known.keySet().iterator().next();
            if (qual == null) return;
            Set<String> cols = known.getOrDefault(qual, Set.of());
            if (!cols.contains(name.toLowerCase(Locale.ROOT))) unknown.add(qual + "." + name);
            super.visit(column);
          }
        });
    return unknown;
  }

  private static void registerFromItem(FromItem item, Map<String, String> aliasToQual, Map<String, Set<String>> known) {
    if (item == null) return;
    if (item instanceof Table table) {
      String qual = SqlUtils.normalizeTableRef(table.getFullyQualifiedName());
      if (qual.contains(".")) {
        aliasToQual.put(qual, qual);
        if (table.getAlias() != null && table.getAlias().getName() != null) {
          aliasToQual.put(table.getAlias().getName().toLowerCase(Locale.ROOT), qual);
        }
        String shortName = qual.substring(qual.indexOf('.') + 1);
        aliasToQual.put(shortName.toLowerCase(Locale.ROOT), qual);
      }
    }
  }
}
