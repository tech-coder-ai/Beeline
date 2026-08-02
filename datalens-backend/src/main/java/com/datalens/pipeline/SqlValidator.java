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
import net.sf.jsqlparser.expression.Expression;
import net.sf.jsqlparser.expression.ExpressionVisitorAdapter;
import net.sf.jsqlparser.expression.Function;
import net.sf.jsqlparser.parser.CCJSqlParserUtil;
import net.sf.jsqlparser.schema.Column;
import net.sf.jsqlparser.schema.Table;
import net.sf.jsqlparser.statement.Statement;
import net.sf.jsqlparser.statement.select.AllColumns;
import net.sf.jsqlparser.statement.select.AllTableColumns;
import net.sf.jsqlparser.statement.select.FromItem;
import net.sf.jsqlparser.statement.select.Join;
import net.sf.jsqlparser.statement.select.OrderByElement;
import net.sf.jsqlparser.statement.select.ParenthesedSelect;
import net.sf.jsqlparser.statement.select.PlainSelect;
import net.sf.jsqlparser.statement.select.Select;
import net.sf.jsqlparser.statement.select.SelectItem;
import net.sf.jsqlparser.statement.select.SetOperationList;
import net.sf.jsqlparser.util.TablesNamesFinder;
import org.springframework.stereotype.Component;

@Component
public class SqlValidator {
  private static final Pattern COMMENT = Pattern.compile("(--|/\\*|\\*/|#(?!\\d))");
  private static final Pattern STACKED = Pattern.compile(";\\s*\\S");

  private final DataLensSettings settings;
  private final com.datalens.model.repository.CatalogDatabaseRepository databases;
  private final com.datalens.model.repository.CatalogTableRepository tables;
  private final com.datalens.model.repository.CatalogColumnRepository catalogColumns;

  public SqlValidator(
      DataLensSettings settings,
      com.datalens.model.repository.CatalogDatabaseRepository databases,
      com.datalens.model.repository.CatalogTableRepository tables,
      com.datalens.model.repository.CatalogColumnRepository catalogColumns) {
    this.settings = settings;
    this.databases = databases;
    this.tables = tables;
    this.catalogColumns = catalogColumns;
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
    if (select instanceof PlainSelect plain) {
      validatePlainSelect(plain, ctx, knownTables, warnings, 0);
      return;
    }
    if (select instanceof SetOperationList setOps) {
      for (Select body : setOps.getSelects()) {
        if (body instanceof PlainSelect plain) {
          validatePlainSelect(plain, ctx, knownTables, warnings, 0);
        }
      }
    }
    if (select instanceof ParenthesedSelect parenthesed && parenthesed.getSelect() != null) {
      validateSelect(parenthesed.getSelect(), ctx, knownTables, warnings);
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
        boolean hasOn = join.getOnExpressions() != null && !join.getOnExpressions().isEmpty();
        boolean hasUsing = join.getUsingColumns() != null && !join.getUsingColumns().isEmpty();
        if (join.isCross() || (!join.isSimple() && !hasOn && !hasUsing)) {
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

    Collector collector = new Collector();
    walkExpressions(plain, collector);

    @SuppressWarnings("unchecked")
    List<String> allowedFns = (List<String>) settings.get("guardrails.allowed_functions", List.of());
    if (allowedFns != null && !allowedFns.isEmpty()) {
      Set<String> allowed = new HashSet<>();
      allowedFns.stream().map(s -> s.toUpperCase(Locale.ROOT)).forEach(allowed::add);
      for (String fn : collector.functions) {
        if (!allowed.contains(fn)) {
          throw new GuardRailViolation("Function " + fn + " is not on the allowlist.");
        }
      }
    }

    if (knownTables != null) {
      List<String> tableRefs = new TablesNamesFinder<Void>().getTableList((Statement) plain);
      Set<String> unknown = new HashSet<>();
      for (String t : tableRefs) {
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
      Set<String> unknownCols = unknownColumns(plain, collector.columns);
      if (!unknownCols.isEmpty()) {
        throw new GuardRailViolation(
            "Query references columns missing from the catalog: "
                + String.join(", ", unknownCols.stream().sorted().toList()));
      }
    }

    for (PlainSelect sub : collectSubSelects(plain, collector)) {
      validatePlainSelect(sub, ctx, knownTables, warnings, depth + 1);
    }
  }

  /** Visits every expression hanging off the select: projection, where, joins, group/having/order. */
  private static void walkExpressions(PlainSelect plain, Collector collector) {
    if (plain.getSelectItems() != null) {
      for (SelectItem<?> item : plain.getSelectItems()) {
        if (item.getExpression() != null) item.getExpression().accept(collector);
        if (item.getAlias() != null && item.getAlias().getName() != null) {
          collector.outputAliases.add(item.getAlias().getName().toLowerCase(Locale.ROOT));
        }
      }
    }
    if (plain.getWhere() != null) plain.getWhere().accept(collector);
    if (plain.getHaving() != null) plain.getHaving().accept(collector);
    if (plain.getJoins() != null) {
      for (Join join : plain.getJoins()) {
        if (join.getOnExpressions() != null) {
          for (Expression on : join.getOnExpressions()) on.accept(collector);
        }
      }
    }
    if (plain.getGroupBy() != null && plain.getGroupBy().getGroupByExpressionList() != null) {
      for (Object e : plain.getGroupBy().getGroupByExpressionList()) {
        if (e instanceof Expression expr) expr.accept(collector);
      }
    }
    if (plain.getOrderByElements() != null) {
      for (OrderByElement o : plain.getOrderByElements()) {
        if (o.getExpression() != null) o.getExpression().accept(collector);
      }
    }
  }

  /** Subselects reachable from the FROM clause plus any found inside expressions. */
  private static List<PlainSelect> collectSubSelects(PlainSelect plain, Collector collector) {
    List<PlainSelect> out = new ArrayList<>(collector.subSelects);
    List<FromItem> fromItems = new ArrayList<>();
    fromItems.add(plain.getFromItem());
    if (plain.getJoins() != null) {
      for (Join join : plain.getJoins()) fromItems.add(join.getRightItem());
    }
    for (FromItem item : fromItems) {
      if (item instanceof ParenthesedSelect sub
          && sub.getSelect() instanceof PlainSelect subPlain
          && !out.contains(subPlain)) {
        out.add(subPlain);
      }
    }
    return out;
  }

  /**
   * Columns that do not exist in the catalog for the table they are referenced against. Uses the
   * FULL catalog column list (not the pruned prompt context) so legitimate columns never fail; a
   * table absent from the catalog is skipped rather than failing every column.
   */
  private Set<String> unknownColumns(PlainSelect plain, List<Column> referencedColumns) {
    Map<String, Set<String>> known = new HashMap<>();
    Map<String, String> aliasToQual = new HashMap<>();
    registerFromItem(plain.getFromItem(), aliasToQual);
    if (plain.getJoins() != null) {
      for (Join join : plain.getJoins()) registerFromItem(join.getRightItem(), aliasToQual);
    }
    for (String qual : new HashSet<>(aliasToQual.values())) {
      known.computeIfAbsent(qual, this::fullCatalogColumns);
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
    for (Column column : referencedColumns) {
      String name = column.getColumnName();
      if (name == null || name.isBlank() || "*".equals(name)) continue;
      String bare = name.replace("`", "").toLowerCase(Locale.ROOT);
      if (outputAliases.contains(bare)) continue;

      String tableRef =
          column.getTable() != null && column.getTable().getName() != null
              ? column.getTable().getName().replace("`", "").toLowerCase(Locale.ROOT)
              : null;
      String qual = tableRef != null ? aliasToQual.get(tableRef) : null;
      if (qual == null && known.size() == 1) qual = known.keySet().iterator().next();
      if (qual == null) continue;
      Set<String> cols = known.getOrDefault(qual, Set.of());
      if (!cols.isEmpty() && !cols.contains(bare)) unknown.add(qual + "." + bare);
    }
    return unknown;
  }

  /** Full lower-cased column names for a db.table qualified name, straight from the catalog. */
  private Set<String> fullCatalogColumns(String qualifiedName) {
    String[] parts = qualifiedName.split("\\.", 2);
    if (parts.length != 2) return Set.of();
    return databases.findAll().stream()
        .filter(db -> db.getName().equalsIgnoreCase(parts[0]))
        .findFirst()
        .flatMap(db -> tables.findByDatabaseIdAndName(db.getId(), parts[1]))
        .map(
            t ->
                catalogColumns.findByTableIdOrderByPositionAsc(t.getId()).stream()
                    .map(c -> c.getName().toLowerCase(Locale.ROOT))
                    .collect(java.util.stream.Collectors.toSet()))
        .orElse(Set.of());
  }

  private static void registerFromItem(FromItem item, Map<String, String> aliasToQual) {
    if (item == null) return;
    if (item instanceof Table table) {
      String qual = SqlUtils.normalizeTableRef(table.getFullyQualifiedName());
      if (qual.contains(".")) {
        aliasToQual.put(qual, qual);
        if (table.getAlias() != null && table.getAlias().getName() != null) {
          aliasToQual.put(table.getAlias().getName().replace("`", "").toLowerCase(Locale.ROOT), qual);
        }
        String shortName = qual.substring(qual.indexOf('.') + 1);
        aliasToQual.put(shortName.toLowerCase(Locale.ROOT), qual);
      }
    }
  }

  /** Gathers function names, column refs, output aliases and subselects from expressions. */
  private static final class Collector extends ExpressionVisitorAdapter<Void> {
    final Set<String> functions = new HashSet<>();
    final List<Column> columns = new ArrayList<>();
    final List<PlainSelect> subSelects = new ArrayList<>();
    final Set<String> outputAliases = new HashSet<>();

    @Override
    public <S> Void visit(Function function, S context) {
      if (function.getName() != null) functions.add(function.getName().toUpperCase(Locale.ROOT));
      return super.visit(function, context);
    }

    @Override
    public <S> Void visit(Column column, S context) {
      columns.add(column);
      return super.visit(column, context);
    }

    @Override
    public <S> Void visit(ParenthesedSelect subSelect, S context) {
      if (subSelect.getSelect() instanceof PlainSelect plain) subSelects.add(plain);
      return null;
    }

    @Override
    public <S> Void visit(Select select, S context) {
      if (select instanceof PlainSelect plain) subSelects.add(plain);
      return null;
    }
  }
}
