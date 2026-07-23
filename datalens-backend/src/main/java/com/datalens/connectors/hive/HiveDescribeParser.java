package com.datalens.connectors.hive;

import com.datalens.connectors.HarvestedColumn;
import com.datalens.connectors.HarvestedTable;
import java.util.ArrayList;
import java.util.List;

final class HiveDescribeParser {
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
      String colName = raw.get(0) == null ? "" : String.valueOf(raw.get(0)).trim();
      String dataType = raw.size() > 1 && raw.get(1) != null ? String.valueOf(raw.get(1)).trim() : "";
      String comment = raw.size() > 2 && raw.get(2) != null ? String.valueOf(raw.get(2)).trim() : "";
      if (colName.startsWith("#")) {
        section = colName.replace("#", "").trim().toLowerCase();
        continue;
      }
      if ("col_name".equalsIgnoreCase(colName) || colName.isEmpty()) continue;
      switch (section) {
        case "col_name", "columns" -> {
          if (dataType.isBlank()) continue;
          columns.add(
              HarvestedColumn.builder()
                  .name(colName)
                  .dataType(dataType)
                  .comment(comment.isBlank() ? null : comment)
                  .position(position++)
                  .build());
        }
        case "partition information" -> partitionNames.add(colName);
        default -> {
          if ("table type:".equalsIgnoreCase(colName)) builder.tableType(dataType.toUpperCase());
          if ("comment:".equalsIgnoreCase(colName)) builder.comment(dataType);
          if ("owner:".equalsIgnoreCase(colName)) builder.owner(dataType);
        }
      }
    }
    builder.columns(columns).partitionColumns(partitionNames);
    return builder.build();
  }
}
