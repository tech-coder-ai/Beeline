package com.datalens.service;

import com.datalens.core.exception.ValidationFailed;
import com.datalens.model.entity.ApprovalItem;
import com.datalens.model.entity.CatalogColumn;
import com.datalens.model.entity.CatalogDatabase;
import com.datalens.model.entity.CatalogTable;
import com.datalens.model.repository.ApprovalItemRepository;
import com.datalens.model.repository.CatalogColumnRepository;
import com.datalens.model.repository.CatalogDatabaseRepository;
import com.datalens.model.repository.CatalogTableRepository;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.BufferedReader;
import java.io.ByteArrayInputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.TreeSet;
import org.apache.poi.ss.usermodel.Row;
import org.apache.poi.ss.usermodel.Sheet;
import org.apache.poi.ss.usermodel.Workbook;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ImportExportService {
  private final CatalogDatabaseRepository databases;
  private final CatalogTableRepository tables;
  private final CatalogColumnRepository columns;
  private final ApprovalItemRepository approvals;
  private final ObjectMapper mapper;

  public ImportExportService(
      CatalogDatabaseRepository databases,
      CatalogTableRepository tables,
      CatalogColumnRepository columns,
      ApprovalItemRepository approvals,
      ObjectMapper mapper) {
    this.databases = databases;
    this.tables = tables;
    this.columns = columns;
    this.approvals = approvals;
    this.mapper = mapper;
  }

  public List<Map<String, String>> parse(String filename, byte[] content) {
    List<Map<String, String>> rows;
    if (filename.toLowerCase().endsWith(".csv")) rows = parseCsv(content);
    else if (filename.toLowerCase().matches(".*\\.(xlsx|xlsm)$")) rows = parseExcel(content);
    else throw new ValidationFailed("Only .csv and .xlsx files are supported");
    if (rows.isEmpty()) throw new ValidationFailed("The file contains no data rows");
    return rows;
  }

  public Map<String, Object> preview(List<Map<String, String>> rows) {
    int matched = 0;
    List<Map<String, Object>> unmatched = new ArrayList<>();
    List<Map<String, Object>> changes = new ArrayList<>();
    for (int i = 0; i < rows.size(); i++) {
      Map<String, String> row = rows.get(i);
      String dbName = row.getOrDefault("database", "");
      String tableName = row.getOrDefault("table", "");
      String columnName = row.getOrDefault("column", "");
      if (tableName.isBlank()) {
        unmatched.add(Map.of("row", i + 1, "reason", "missing table name"));
        continue;
      }
      Optional<ResolvedTable> resolved = findTable(dbName, tableName);
      if (resolved.isEmpty()) {
        unmatched.add(
            Map.of(
                "row",
                i + 1,
                "reason",
                "table '" + dbName + "." + tableName + "' not in catalog"));
        continue;
      }
      CatalogTable table = resolved.get().table();
      CatalogDatabase database = resolved.get().database();
      CatalogColumn targetColumn = null;
      if (!columnName.isBlank()) {
        List<CatalogColumn> tableColumns = columns.findByTableIdOrderByPositionAsc(table.getId());
        targetColumn =
            tableColumns.stream().filter(c -> c.getName().equals(columnName)).findFirst().orElse(null);
        if (targetColumn == null) {
          unmatched.add(
              Map.of("row", i + 1, "reason", "column '" + columnName + "' not in " + tableName));
          continue;
        }
      }
      matched++;
      changes.addAll(diff(row, database, table, targetColumn));
    }
    return Map.of("matched_rows", matched, "unmatched", unmatched, "changes", changes);
  }

  @Transactional
  public Map<String, Object> commit(List<Map<String, String>> rows) {
    Map<String, Object> preview = preview(rows);
    @SuppressWarnings("unchecked")
    List<Map<String, Object>> changes = (List<Map<String, Object>>) preview.get("changes");
    int queued = 0;
    for (Map<String, Object> change : changes) {
      ApprovalItem item = new ApprovalItem();
      item.setEntityType(String.valueOf(change.get("entity_type")));
      item.setEntityId(String.valueOf(change.get("entity_id")));
      item.setEntityLabel(String.valueOf(change.get("label")));
      item.setField(String.valueOf(change.get("field")));
      item.setCurrentValue(change.get("current") == null ? null : String.valueOf(change.get("current")));
      item.setProposedValue(String.valueOf(change.get("proposed")));
      item.setProposedPayload(change.get("payload"));
      item.setSource("import");
      item.setConfidence(1.0);
      item.setRationale("Imported from uploaded file");
      item.setStatus("pending");
      approvals.save(item);
      queued++;
    }
    Map<String, Object> result = new LinkedHashMap<>(preview);
    result.put("queued_for_approval", queued);
    return result;
  }

  private List<Map<String, Object>> diff(
      Map<String, String> row, CatalogDatabase database, CatalogTable table, CatalogColumn column) {
    List<Map<String, Object>> changes = new ArrayList<>();
    String label =
        database.getName()
            + "."
            + table.getName()
            + (column != null ? "." + column.getName() : "");

    if (column != null) {
      maybeAdd(
          changes,
          label,
          "column_description",
          column.getId(),
          "description",
          column.getDescription(),
          row.get("description"));
    } else {
      maybeAdd(
          changes,
          label,
          "table_description",
          table.getId(),
          "description",
          table.getDescription(),
          row.get("description"));
      maybeAdd(
          changes,
          label,
          "classification",
          table.getId(),
          "classification",
          table.getClassification(),
          row.get("classification"));
      if (row.get("tags") != null && !row.get("tags").isBlank()) {
        TreeSet<String> proposedTags = new TreeSet<>();
        for (String tag : row.get("tags").split(",")) {
          if (!tag.trim().isBlank()) proposedTags.add(tag.trim());
        }
        try {
          String currentTags = mapper.writeValueAsString(table.getTags() == null ? List.of() : table.getTags());
          String proposed = mapper.writeValueAsString(proposedTags.stream().toList());
          maybeAdd(changes, label, "tag", table.getId(), "tags", currentTags, proposed);
        } catch (JsonProcessingException ignored) {
        }
      }
    }
    if (row.get("glossary") != null && !row.get("glossary").isBlank()) {
      maybeAdd(changes, label, "glossary_term", table.getId(), "glossary", null, row.get("glossary"));
    }
    return changes;
  }

  private void maybeAdd(
      List<Map<String, Object>> changes,
      String label,
      String entityType,
      String entityId,
      String field,
      String current,
      String proposed) {
    if (proposed == null || proposed.isBlank()) return;
    if (Objects.equals(proposed, current == null ? "" : current)) return;
    Map<String, Object> change = new LinkedHashMap<>();
    change.put("entity_type", entityType);
    change.put("entity_id", entityId);
    change.put("label", label);
    change.put("field", field);
    change.put("current", current);
    change.put("proposed", proposed);
    changes.add(change);
  }

  private Optional<ResolvedTable> findTable(String databaseName, String tableName) {
    if (tableName == null || tableName.isBlank()) return Optional.empty();
    for (CatalogTable table : tables.findByIsActiveTrueOrderByUsageCountDescNameAsc()) {
      if (!table.getName().equals(tableName)) continue;
      Optional<CatalogDatabase> db = databases.findById(table.getDatabaseId());
      if (db.isEmpty()) continue;
      if (databaseName != null && !databaseName.isBlank() && !db.get().getName().equals(databaseName)) {
        continue;
      }
      return Optional.of(new ResolvedTable(db.get(), table));
    }
    return Optional.empty();
  }

  private List<Map<String, String>> parseCsv(byte[] content) {
    List<Map<String, String>> rows = new ArrayList<>();
    try (BufferedReader br =
        new BufferedReader(
            new InputStreamReader(new ByteArrayInputStream(content), StandardCharsets.UTF_8))) {
      String headerLine = br.readLine();
      if (headerLine == null) return rows;
      headerLine = stripBom(headerLine);
      List<String> headers =
          parseCsvLine(headerLine).stream().map(h -> h.trim().toLowerCase()).toList();
      String line;
      while ((line = br.readLine()) != null) {
        if (line.isBlank()) continue;
        List<String> cells = parseCsvLine(line);
        Map<String, String> row = new HashMap<>();
        for (int i = 0; i < headers.size() && i < cells.size(); i++) {
          row.put(headers.get(i), cells.get(i).trim());
        }
        if (row.values().stream().anyMatch(v -> v != null && !v.isBlank())) rows.add(row);
      }
    } catch (Exception e) {
      throw new ValidationFailed("Failed to parse CSV: " + e.getMessage());
    }
    return rows;
  }

  private List<Map<String, String>> parseExcel(byte[] content) {
    List<Map<String, String>> rows = new ArrayList<>();
    try (Workbook wb = new XSSFWorkbook(new ByteArrayInputStream(content))) {
      Sheet sheet = wb.getSheetAt(0);
      Row header = sheet.getRow(0);
      if (header == null) return rows;
      List<String> headers = new ArrayList<>();
      header.forEach(c -> headers.add(String.valueOf(c).trim().toLowerCase()));
      for (int r = 1; r <= sheet.getLastRowNum(); r++) {
        Row row = sheet.getRow(r);
        if (row == null) continue;
        Map<String, String> map = new HashMap<>();
        boolean any = false;
        for (int c = 0; c < headers.size(); c++) {
          String value = row.getCell(c) == null ? "" : row.getCell(c).toString().trim();
          map.put(headers.get(c), value);
          if (!value.isBlank()) any = true;
        }
        if (any) rows.add(map);
      }
    } catch (Exception e) {
      throw new ValidationFailed("Failed to parse Excel: " + e.getMessage());
    }
    return rows;
  }

  private static String stripBom(String line) {
    if (line.startsWith("\uFEFF")) return line.substring(1);
    return line;
  }

  /** Parses one CSV line, respecting double-quoted fields that may contain commas. */
  static List<String> parseCsvLine(String line) {
    List<String> result = new ArrayList<>();
    StringBuilder current = new StringBuilder();
    boolean inQuotes = false;
    for (int i = 0; i < line.length(); i++) {
      char ch = line.charAt(i);
      if (ch == '"') {
        if (inQuotes && i + 1 < line.length() && line.charAt(i + 1) == '"') {
          current.append('"');
          i++;
        } else {
          inQuotes = !inQuotes;
        }
      } else if (ch == ',' && !inQuotes) {
        result.add(current.toString());
        current.setLength(0);
      } else {
        current.append(ch);
      }
    }
    result.add(current.toString());
    return result;
  }

  private record ResolvedTable(CatalogDatabase database, CatalogTable table) {}
}
