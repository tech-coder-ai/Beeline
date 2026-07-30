package com.datalens.connectors.hive;

import com.datalens.connectors.HarvestedColumn;
import com.datalens.connectors.HarvestedTable;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Set;

/** Parses Hive {@code DESCRIBE FORMATTED} output (Python connector parity). */
final class HiveDescribeParser {
  private static final Set<String> TABLE_PARAM_KEYS =
      Set.of("numrows", "totalsize", "rawdatasize", "transient_lastddltime", "comment");

  private HiveDescribeParser() {}

  static HarvestedTable parse(String database, String table, List<List<Object>> rows) {
    HarvestedTable.HarvestedTableBuilder builder =
        HarvestedTable.builder().database(database).name(table);
    String section = "columns";
    int position = 0;
    List<String> partitionNames = new ArrayList<>();
    List<HarvestedColumn> columns = new ArrayList<>();

    for (List<Object> raw : rows) {
      if (raw.isEmpty()) continue;
      String col0 = raw.get(0) == null ? "" : String.valueOf(raw.get(0)).trim();
      String col1 = raw.size() > 1 && raw.get(1) != null ? String.valueOf(raw.get(1)).trim() : "";
      String col2 = raw.size() > 2 && raw.get(2) != null ? String.valueOf(raw.get(2)).trim() : "";

      if (col0.startsWith("#")) {
        section = col0.substring(1).trim().toLowerCase(Locale.ROOT);
        continue;
      }
      if (col0.isEmpty() && col1.isEmpty()) continue;
      if ("col_name".equalsIgnoreCase(col0)) continue;

      switch (section) {
        case "col_name", "columns" -> {
          if (col0.isBlank() || col1.isBlank()) continue;
          columns.add(
              HarvestedColumn.builder()
                  .name(col0)
                  .dataType(col1)
                  .comment(col2.isBlank() ? null : col2)
                  .position(position++)
                  .build());
        }
        case "partition information" -> {
          if (col0.isBlank() || col1.isBlank()) continue;
          partitionNames.add(col0);
          columns.add(
              HarvestedColumn.builder()
                  .name(col0)
                  .dataType(col1)
                  .comment(col2.isBlank() ? null : col2)
                  .isPartition(true)
                  .position(position++)
                  .build());
        }
        case "detailed table information", "table information" -> applyDetailRow(builder, col0, col1, col2);
        case "table parameters", "storage information" -> applyTableParameter(builder, col0, col1, col2);
        default -> {
          if (col0.endsWith(":")) applyDetailRow(builder, col0, col1, col2);
        }
      }
    }

    builder.columns(columns).partitionColumns(partitionNames);
    return builder.build();
  }

  private static void applyDetailRow(
      HarvestedTable.HarvestedTableBuilder builder, String col0, String col1, String col2) {
    if (col0.isBlank() && TABLE_PARAM_KEYS.contains(col1.toLowerCase(Locale.ROOT))) {
      applyTableParameter(builder, col0, col1, col2);
      return;
    }
    String key = col0.endsWith(":") ? col0.substring(0, col0.length() - 1).trim() : col0;
    switch (key.toLowerCase(Locale.ROOT)) {
      case "owner" -> builder.owner(col1);
      case "table type" -> builder.tableType(col1.toUpperCase(Locale.ROOT).contains("VIEW") ? "VIEW" : "TABLE");
      case "comment" -> builder.comment(col1);
      case "inputformat" -> {
        String fmt = col1.contains(".") ? col1.substring(col1.lastIndexOf('.') + 1) : col1;
        builder.storageFormat(fmt.replace("InputFormat", ""));
      }
      case "compressed" -> builder.compression(col1);
      default -> {}
    }
  }

  private static void applyTableParameter(
      HarvestedTable.HarvestedTableBuilder builder, String col0, String col1, String col2) {
    String param = col0.isBlank() ? col1 : col0;
    String value = col0.isBlank() ? col2 : col1;
    if (param.isBlank()) return;
    switch (param.toLowerCase(Locale.ROOT)) {
      case "numrows" -> builder.rowCount(parseIntValue(value));
      case "totalsize" -> builder.sizeBytes(parseLongBytes(value));
      case "comment" -> {
        if (!value.isBlank()) builder.comment(value);
      }
      default -> {}
    }
  }

  private static Integer parseIntValue(String raw) {
    if (raw == null || raw.isBlank()) return null;
    try {
      long value = Long.parseLong(raw.replace(",", "").trim());
      if (value > Integer.MAX_VALUE) return Integer.MAX_VALUE;
      return (int) value;
    } catch (NumberFormatException e) {
      return null;
    }
  }

  private static Long parseLongBytes(String raw) {
    if (raw == null || raw.isBlank()) return null;
    try {
      return Long.parseLong(raw.replace(",", "").trim());
    } catch (NumberFormatException e) {
      return null;
    }
  }
}
