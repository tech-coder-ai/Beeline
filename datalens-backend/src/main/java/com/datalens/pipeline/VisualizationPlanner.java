package com.datalens.pipeline;

import com.datalens.config.DataLensSettings;
import com.datalens.schema.response.ChartSeriesDto;
import com.datalens.schema.response.ChartSpecDto;
import com.datalens.schema.response.KpiCardDto;
import com.datalens.schema.response.TableColumnDto;
import com.datalens.schema.response.TableSpecDto;
import java.math.BigDecimal;
import java.time.temporal.Temporal;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.springframework.stereotype.Component;

/** Deterministic chart/table selection from query result shape (Python parity). */
@Component
public class VisualizationPlanner {
  private static final Set<String> NUMERIC_TYPES =
      Set.of("int", "integer", "bigint", "smallint", "tinyint", "float", "double", "decimal", "numeric", "real", "number");
  private static final Set<String> DATE_TYPES = Set.of("date", "timestamp", "datetime");
  private static final Pattern DATE_NAME_HINT =
      Pattern.compile("(date|month|year|week|quarter|day|period|time)", Pattern.CASE_INSENSITIVE);
  private static final Pattern DATE_STRING = Pattern.compile("^\\d{4}([-/]\\d{1,2}){1,2}");

  private static final Set<String> CHART_PRIMARY_INTENTS =
      Set.of(
          "time_series",
          "trend",
          "comparison",
          "yoy",
          "mom",
          "qoq",
          "distribution",
          "grouping",
          "top_n",
          "bottom_n",
          "ranking",
          "correlation",
          "cumulative_sum",
          "running_total",
          "rolling_average",
          "forecasting",
          "anomaly",
          "aggregation");
  private static final Set<String> TABLE_PRIMARY_INTENTS =
      Set.of(
          "lookup",
          "filtering",
          "exploration",
          "distinct_count",
          "summarization",
          "median",
          "stddev",
          "variance",
          "window",
          "percentile");
  private static final Pattern PROMPT_TABLE_HINT =
      Pattern.compile("\\b(list|show me|details|rows|records|breakdown|tabular|table data)\\b", Pattern.CASE_INSENSITIVE);
  private static final Pattern PROMPT_CHART_HINT =
      Pattern.compile("\\b(trend|over time|chart|graph|plot|visuali[sz]e|histogram)\\b", Pattern.CASE_INSENSITIVE);

  private final DataLensSettings settings;

  public VisualizationPlanner(DataLensSettings settings) {
    this.settings = settings;
  }

  public VisualizationResult run(PipelineContext ctx) {
    List<String> columns = ctx.getResultColumns();
    List<List<Object>> rows = ctx.getResultRows();
    if (columns == null || columns.isEmpty()) {
      return new VisualizationResult("text", List.of(), List.of(), null);
    }

    List<List<Object>> colValues = new ArrayList<>();
    for (int i = 0; i < columns.size(); i++) {
      int idx = i;
      colValues.add(rows.stream().map(r -> idx < r.size() ? r.get(idx) : null).toList());
    }
    List<String> types =
        ctx.getResultTypes() != null && !ctx.getResultTypes().isEmpty()
            ? ctx.getResultTypes()
            : columns.stream().map(c -> "string").toList();
    List<ColumnProfile> profiles = new ArrayList<>();
    for (int i = 0; i < columns.size(); i++) {
      profiles.add(new ColumnProfile(columns.get(i), types.get(i), colValues.get(i)));
    }

    TableSpecDto table = null;
    List<Integer> temporal = indicesWhere(profiles, ColumnProfile::isTemporal);
    List<Integer> numeric = indicesWhere(profiles, ColumnProfile::isNumeric);
    List<Integer> categorical = indicesWhere(profiles, ColumnProfile::isCategorical);

    List<KpiCardDto> cards = new ArrayList<>();
    List<ChartSpecDto> charts = new ArrayList<>();
    int kpiMax = ((Number) settings.get("visualization.kpi_max_values", 6)).intValue();
    Set<String> intentTypes = intentTypes(ctx);

    if (rows.size() == 1 && !numeric.isEmpty()) {
      for (int i : numeric.stream().limit(kpiMax).toList()) {
        Double value = toNumber(rows.get(0).get(i));
        KpiCardDto card = new KpiCardDto();
        card.setLabel(pretty(columns.get(i)));
        card.setValue(formatNumber(value));
        card.setRawValue(value);
        cards.add(card);
      }
      return new VisualizationResult("kpi", cards, charts, null);
    }

    if (!temporal.isEmpty() && !numeric.isEmpty() && rows.size() > 1) {
      charts.add(timeChart(columns, rows, temporal.get(0), numeric, intentTypes));
    } else if (!categorical.isEmpty() && !numeric.isEmpty() && rows.size() > 1) {
      int cat = categorical.stream().min(Comparator.comparingInt(i -> profiles.get(i).distinct)).orElse(categorical.get(0));
      int maxPie = ((Number) settings.get("visualization.max_categories_pie", 8)).intValue();
      int maxBar = ((Number) settings.get("visualization.max_categories_bar", 30)).intValue();
      boolean wantsShare =
          (intentTypes.contains("distribution") || intentTypes.contains("grouping")) && numeric.size() == 1;
      if (categorical.size() >= 2 && !numeric.isEmpty() && profiles.get(cat).distinct <= 20) {
        ChartSpecDto heat = heatmap(columns, rows, categorical.get(0), categorical.get(1), numeric.get(0));
        if (heat != null) charts.add(heat);
      }
      if (charts.isEmpty() && wantsShare && profiles.get(cat).distinct <= maxPie) {
        charts.add(pieChart(columns, rows, cat, numeric.get(0)));
      }
      if (charts.isEmpty() && profiles.get(cat).distinct <= maxBar) {
        charts.add(barChart(columns, rows, cat, numeric, intentTypes));
      }
    } else if (numeric.size() >= 2 && rows.size() > 5
        && (intentTypes.contains("correlation") || categorical.isEmpty())) {
      int maxPts = ((Number) settings.get("visualization.max_points_scatter", 5000)).intValue();
      ChartSpecDto scatter = new ChartSpecDto();
      scatter.setChartType("scatter");
      scatter.setTitle(pretty(columns.get(numeric.get(1))) + " vs " + pretty(columns.get(numeric.get(0))));
      ChartSeriesDto series = new ChartSeriesDto();
      series.setName("points");
      List<Object> points = new ArrayList<>();
      for (List<Object> row : rows.stream().limit(maxPts).toList()) {
        points.add(List.of(toNumber(row.get(numeric.get(0))), toNumber(row.get(numeric.get(1)))));
      }
      series.setData(points);
      scatter.getSeries().add(series);
      scatter.setXLabel(pretty(columns.get(numeric.get(0))));
      scatter.setYLabel(pretty(columns.get(numeric.get(1))));
      charts.add(scatter);
    }

    if (shouldIncludeTable(ctx, charts, columns, rows, intentTypes)) {
      table = tableSpec(ctx, profiles);
    }

    String viz;
    if (!charts.isEmpty()) {
      viz = table != null && rows.size() > 1 ? "mixed" : charts.get(0).getChartType();
    } else if (rows.size() > 1) {
      viz = "grid";
    } else if (!rows.isEmpty()) {
      viz = cards.isEmpty() ? "grid" : "kpi";
    } else {
      viz = "text";
    }
    return new VisualizationResult(viz, cards, charts, table);
  }

  /** Include the data grid when the question calls for tabular detail, not when a chart alone answers it. */
  private boolean shouldIncludeTable(
      PipelineContext ctx,
      List<ChartSpecDto> charts,
      List<String> columns,
      List<List<Object>> rows,
      Set<String> intentTypes) {
    if (rows.isEmpty()) return false;
    if (charts.isEmpty()) return true;

    if (intentTypes.stream().anyMatch(TABLE_PRIMARY_INTENTS::contains)) return true;
    if (intentTypes.stream().anyMatch(CHART_PRIMARY_INTENTS::contains)) return false;

    String prompt = ctx.effectivePrompt();
    if (prompt != null && PROMPT_TABLE_HINT.matcher(prompt).find()) return true;
    if (prompt != null && PROMPT_CHART_HINT.matcher(prompt).find()) return false;

    if (columns.size() > 4) return true;
    if (rows.size() > 25) return false;

    return false;
  }

  private TableSpecDto tableSpec(PipelineContext ctx, List<ColumnProfile> profiles) {
    TableSpecDto table = new TableSpecDto();
    for (ColumnProfile p : profiles) {
      TableColumnDto col = new TableColumnDto();
      col.setField(p.name);
      col.setHeader(pretty(p.name));
      col.setDataType(p.isTemporal() ? "date" : (p.isNumeric() ? "number" : "string"));
      col.setMetric(p.isNumeric());
      table.getColumns().add(col);
    }
    for (List<Object> row : ctx.getResultRows()) {
      Map<String, Object> map = new HashMap<>();
      for (int i = 0; i < profiles.size(); i++) {
        Object val = i < row.size() ? row.get(i) : null;
        map.put(profiles.get(i).name, jsonSafe(val));
      }
      table.getRows().add(map);
    }
    table.setTotalRows(ctx.getRowCount());
    table.setTruncated(ctx.isTruncated());
    return table;
  }

  private ChartSpecDto timeChart(
      List<String> columns, List<List<Object>> rows, int tIdx, List<Integer> numeric, Set<String> intentTypes) {
    List<List<Object>> ordered = new ArrayList<>(rows);
    ordered.sort(Comparator.comparing(r -> String.valueOf(r.get(tIdx))));
    String chartType =
        intentTypes.contains("cumulative_sum") || intentTypes.contains("running_total") ? "area" : "line";
    ChartSpecDto chart = new ChartSpecDto();
    chart.setChartType(chartType);
    chart.setTitle(pretty(columns.get(numeric.get(0))) + " over time");
    chart.setCategories(objectList(ordered.stream().map(r -> String.valueOf(r.get(tIdx))).toList()));
    for (int i : numeric.stream().limit(4).toList()) {
      ChartSeriesDto s = new ChartSeriesDto();
      s.setName(pretty(columns.get(i)));
      s.setData(objectList(ordered.stream().map(r -> toNumber(r.get(i))).toList()));
      chart.getSeries().add(s);
    }
    chart.setXLabel(pretty(columns.get(tIdx)));
    return chart;
  }

  private ChartSpecDto barChart(
      List<String> columns, List<List<Object>> rows, int cat, List<Integer> numeric, Set<String> intentTypes) {
    int primary = numeric.get(0);
    List<List<Object>> ordered = new ArrayList<>(rows);
    ordered.sort(Comparator.comparingDouble(r -> -(toNumber(r.get(primary)) != null ? toNumber(r.get(primary)) : 0)));
    ChartSpecDto chart = new ChartSpecDto();
    chart.setChartType("bar");
    chart.setTitle(pretty(columns.get(primary)) + " by " + pretty(columns.get(cat)));
    chart.setCategories(objectList(ordered.stream().map(r -> String.valueOf(r.get(cat))).toList()));
    for (int i : numeric.stream().limit(3).toList()) {
      ChartSeriesDto s = new ChartSeriesDto();
      s.setName(pretty(columns.get(i)));
      s.setData(objectList(ordered.stream().map(r -> toNumber(r.get(i))).toList()));
      chart.getSeries().add(s);
    }
    chart.setXLabel(pretty(columns.get(cat)));
    return chart;
  }

  private ChartSpecDto pieChart(List<String> columns, List<List<Object>> rows, int cat, int metric) {
    ChartSpecDto chart = new ChartSpecDto();
    chart.setChartType("donut");
    chart.setTitle(pretty(columns.get(metric)) + " share by " + pretty(columns.get(cat)));
    ChartSeriesDto s = new ChartSeriesDto();
    s.setName(pretty(columns.get(metric)));
    List<Object> data = new ArrayList<>();
    for (List<Object> row : rows) {
      Map<String, Object> point = new HashMap<>();
      point.put("name", String.valueOf(row.get(cat)));
      point.put("value", toNumber(row.get(metric)));
      data.add(point);
    }
    s.setData(data);
    chart.getSeries().add(s);
    return chart;
  }

  private ChartSpecDto heatmap(List<String> columns, List<List<Object>> rows, int catA, int catB, int metric) {
    List<String> xs = rows.stream().map(r -> String.valueOf(r.get(catA))).distinct().sorted().toList();
    List<String> ys = rows.stream().map(r -> String.valueOf(r.get(catB))).distinct().sorted().toList();
    if (xs.size() > 30 || ys.size() > 30) return null;
    List<Object> data = new ArrayList<>();
    for (List<Object> row : rows) {
      data.add(
          List.of(
              xs.indexOf(String.valueOf(row.get(catA))),
              ys.indexOf(String.valueOf(row.get(catB))),
              toNumber(row.get(metric)) != null ? toNumber(row.get(metric)) : 0));
    }
    ChartSpecDto chart = new ChartSpecDto();
    chart.setChartType("heatmap");
    chart.setTitle(
        pretty(columns.get(metric)) + ": " + pretty(columns.get(catA)) + " × " + pretty(columns.get(catB)));
    chart.setCategories(objectList(xs));
    ChartSeriesDto s = new ChartSeriesDto();
    s.setName(pretty(columns.get(catB)));
    s.setData(data);
    chart.getSeries().add(s);
    chart.setXLabel(pretty(columns.get(catA)));
    chart.setYLabel(pretty(columns.get(catB)));
    return chart;
  }

  private static List<Object> objectList(List<?> source) {
    return new ArrayList<>(source);
  }

  private static Set<String> intentTypes(PipelineContext ctx) {
    if (ctx.getIntent() == null || ctx.getIntent().getIntentTypes() == null) return Set.of();
    Set<String> out = new HashSet<>();
    for (String t : ctx.getIntent().getIntentTypes()) {
      if (t != null) out.add(t.toLowerCase(Locale.ROOT));
    }
    return out;
  }

  private static List<Integer> indicesWhere(List<ColumnProfile> profiles, java.util.function.Predicate<ColumnProfile> pred) {
    List<Integer> out = new ArrayList<>();
    for (int i = 0; i < profiles.size(); i++) {
      if (pred.test(profiles.get(i))) out.add(i);
    }
    return out;
  }

  private static String baseType(String raw) {
    if (raw == null) return "";
    return raw.replaceAll("[(<].*", "").toLowerCase(Locale.ROOT).trim();
  }

  private static boolean isNumericValue(Object value) {
    if (value == null || value instanceof Boolean) return false;
    if (value instanceof Number) return true;
    if (value instanceof String s) {
      try {
        Double.parseDouble(s.replace(",", ""));
        return true;
      } catch (NumberFormatException e) {
        return false;
      }
    }
    return false;
  }

  private static Double toNumber(Object value) {
    if (value == null || value instanceof Boolean) return null;
    if (value instanceof Number n) return n.doubleValue();
    if (value instanceof String s) {
      try {
        return Double.parseDouble(s.replace(",", ""));
      } catch (NumberFormatException e) {
        return null;
      }
    }
    return null;
  }

  private static Object jsonSafe(Object value) {
    if (value == null) return null;
    if (value instanceof String || value instanceof Number || value instanceof Boolean) return value;
    if (value instanceof BigDecimal bd) return bd.doubleValue();
    if (value instanceof Temporal) return value.toString();
    if (value instanceof java.util.Date d) return d.toInstant().toString();
    return String.valueOf(value);
  }

  private static String pretty(String name) {
    if (name == null || name.isBlank()) return "";
    String[] parts = name.replace('_', ' ').trim().split("\\s+");
    StringBuilder sb = new StringBuilder();
    for (String p : parts) {
      if (p.isEmpty()) continue;
      if (!sb.isEmpty()) sb.append(' ');
      sb.append(Character.toUpperCase(p.charAt(0)));
      if (p.length() > 1) sb.append(p.substring(1).toLowerCase(Locale.ROOT));
    }
    return sb.toString();
  }

  private static String formatNumber(Double value) {
    if (value == null) return "-";
    double v = value;
    if (Math.abs(v) >= 1_000_000_000) return String.format(Locale.US, "%.2fB", v / 1_000_000_000);
    if (Math.abs(v) >= 1_000_000) return String.format(Locale.US, "%.2fM", v / 1_000_000);
    if (Math.abs(v) >= 10_000) return String.format(Locale.US, "%.1fK", v / 1_000);
    if (v == Math.rint(v)) return String.format(Locale.US, "%,.0f", v);
    return String.format(Locale.US, "%,.2f", v);
  }

  private static final class ColumnProfile {
    private final String name;
    private final boolean temporal;
    private final boolean numeric;
    private final boolean categorical;
    private final int distinct;

    ColumnProfile(String name, String declaredType, List<Object> values) {
      this.name = name;
      String base = baseType(declaredType);
      List<Object> nonNull = values.stream().filter(v -> v != null).toList();
      boolean numericSample =
          !nonNull.isEmpty() && nonNull.stream().limit(20).allMatch(VisualizationPlanner::isNumericValue);
      this.temporal =
          DATE_TYPES.contains(base)
              || (DATE_NAME_HINT.matcher(name).find() && !numericLooking(nonNull))
              || nonNull.stream().limit(5).anyMatch(v -> v instanceof Temporal || v instanceof java.util.Date)
              || looksLikeDates(nonNull.stream().limit(10).toList());
      this.numeric = !temporal && (NUMERIC_TYPES.contains(base) || numericSample);
      this.categorical = !temporal && !numeric;
      this.distinct = (int) nonNull.stream().map(String::valueOf).distinct().count();
    }

    boolean isTemporal() {
      return temporal;
    }

    boolean isNumeric() {
      return numeric;
    }

    boolean isCategorical() {
      return categorical;
    }

    private static boolean numericLooking(List<Object> nonNull) {
      return !nonNull.isEmpty() && nonNull.stream().limit(5).allMatch(VisualizationPlanner::isNumericValue);
    }

    private static boolean looksLikeDates(List<Object> values) {
      List<String> strs = values.stream().filter(v -> v instanceof String).map(String::valueOf).toList();
      return !strs.isEmpty() && strs.stream().allMatch(s -> DATE_STRING.matcher(s).matches());
    }
  }

  public record VisualizationResult(
      String visualization, List<KpiCardDto> cards, List<ChartSpecDto> charts, TableSpecDto table) {

    public Map<String, Object> toMap() {
      Map<String, Object> out = new HashMap<>();
      out.put("visualization", visualization);
      out.put("cards", cards);
      out.put("charts", charts);
      out.put("table", table);
      return out;
    }
  }
}
