package com.datalens.service;

import com.datalens.core.exception.ValidationFailed;
import com.datalens.model.entity.ApprovalItem;
import com.datalens.model.entity.CatalogColumn;
import com.datalens.model.entity.CatalogTable;
import com.datalens.model.repository.ApprovalItemRepository;
import com.datalens.model.repository.CatalogColumnRepository;
import com.datalens.model.repository.CatalogDatabaseRepository;
import com.datalens.model.repository.CatalogTableRepository;
import java.io.BufferedReader;
import java.io.ByteArrayInputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
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

  public ImportExportService(
      CatalogDatabaseRepository databases,
      CatalogTableRepository tables,
      CatalogColumnRepository columns,
      ApprovalItemRepository approvals) {
    this.databases = databases;
    this.tables = tables;
    this.columns = columns;
    this.approvals = approvals;
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
      String tableName = row.getOrDefault("table", "");
      if (tableName.isBlank()) {
        unmatched.add(Map.of("row", i + 1, "reason", "missing table name"));
        continue;
      }
      CatalogTable table = findTable(row.get("database"), tableName);
      if (table == null) {
        unmatched.add(Map.of("row", i + 1, "reason", "table not in catalog"));
        continue;
      }
      matched++;
      if (row.get("description") != null && !row.get("description").isBlank()) {
        changes.add(Map.of("entity", table.getName(), "field", "description", "value", row.get("description")));
      }
    }
    return Map.of("matched_rows", matched, "unmatched", unmatched, "changes", changes);
  }

  @Transactional
  public Map<String, Object> commit(List<Map<String, String>> rows) {
    int proposals = 0;
    for (Map<String, String> row : rows) {
      CatalogTable table = findTable(row.get("database"), row.get("table"));
      if (table == null) continue;
      if (row.get("description") != null && !row.get("description").isBlank()) {
        ApprovalItem item = new ApprovalItem();
        item.setEntityType("table_description");
        item.setEntityId(table.getId());
        item.setEntityLabel(table.getName());
        item.setField("description");
        item.setCurrentValue(table.getDescription());
        item.setProposedValue(row.get("description"));
        item.setSource("import");
        approvals.save(item);
        proposals++;
      }
    }
    return Map.of("proposals", proposals);
  }

  private CatalogTable findTable(String database, String tableName) {
    if (tableName == null || tableName.isBlank()) return null;
    for (CatalogTable t : tables.findAll()) {
      if (!t.getName().equalsIgnoreCase(tableName)) continue;
      if (database == null || database.isBlank()) return t;
      var db = databases.findById(t.getDatabaseId());
      if (db.isPresent() && db.get().getName().equalsIgnoreCase(database)) return t;
    }
    return null;
  }

  private List<Map<String, String>> parseCsv(byte[] content) {
    List<Map<String, String>> rows = new ArrayList<>();
    try (BufferedReader br =
        new BufferedReader(new InputStreamReader(new ByteArrayInputStream(content), StandardCharsets.UTF_8))) {
      String headerLine = br.readLine();
      if (headerLine == null) return rows;
      String[] headers = headerLine.split(",");
      String line;
      while ((line = br.readLine()) != null) {
        String[] cells = line.split(",", -1);
        Map<String, String> row = new HashMap<>();
        for (int i = 0; i < headers.length && i < cells.length; i++) {
          row.put(headers[i].trim().toLowerCase(), cells[i].trim());
        }
        rows.add(row);
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
        for (int c = 0; c < headers.size(); c++) {
          map.put(headers.get(c), row.getCell(c) == null ? "" : row.getCell(c).toString().trim());
        }
        rows.add(map);
      }
    } catch (Exception e) {
      throw new ValidationFailed("Failed to parse Excel: " + e.getMessage());
    }
    return rows;
  }
}
