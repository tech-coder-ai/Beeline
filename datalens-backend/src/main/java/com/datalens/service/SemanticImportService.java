package com.datalens.service;

import com.datalens.core.exception.ValidationFailed;
import com.datalens.model.entity.Abbreviation;
import com.datalens.model.entity.BusinessTerm;
import com.datalens.model.entity.GlossaryTerm;
import com.datalens.model.entity.Synonym;
import com.datalens.model.repository.AbbreviationRepository;
import com.datalens.model.repository.BusinessTermRepository;
import com.datalens.model.repository.CatalogDatabaseRepository;
import com.datalens.model.repository.CatalogTableRepository;
import com.datalens.model.repository.GlossaryTermRepository;
import com.datalens.model.repository.SynonymRepository;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class SemanticImportService {
  private final ImportExportService metadataImport;
  private final GlossaryTermRepository glossary;
  private final SynonymRepository synonyms;
  private final BusinessTermRepository businessTerms;
  private final AbbreviationRepository abbreviations;
  private final CatalogTableRepository tables;
  private final CatalogDatabaseRepository databases;

  public SemanticImportService(
      ImportExportService metadataImport,
      GlossaryTermRepository glossary,
      SynonymRepository synonyms,
      BusinessTermRepository businessTerms,
      AbbreviationRepository abbreviations,
      CatalogTableRepository tables,
      CatalogDatabaseRepository databases) {
    this.metadataImport = metadataImport;
    this.glossary = glossary;
    this.synonyms = synonyms;
    this.businessTerms = businessTerms;
    this.abbreviations = abbreviations;
    this.tables = tables;
    this.databases = databases;
  }

  public List<Map<String, String>> parse(String filename, byte[] content) {
    return metadataImport.parse(filename, content);
  }

  public String detectType(List<Map<String, String>> rows) {
    if (rows.isEmpty()) throw new ValidationFailed("The file contains no data rows");
    Set<String> keys = rows.get(0).keySet();
    if (keys.contains("abbreviation")
            && (keys.contains("entity") || keys.contains("canonical"))
        || keys.contains("abbrev") && (keys.contains("entity") || keys.contains("canonical"))) {
      return "abbreviations";
    }
    if (keys.contains("term") && keys.contains("entity") && keys.contains("column_name") && keys.contains("value")) {
      return "business_terms";
    }
    if (keys.contains("canonical") && (keys.contains("synonym") || keys.contains("synonyms"))) {
      return "synonyms";
    }
    if (keys.contains("table")) return "metadata";
    throw new ValidationFailed(
        "Could not detect import type. Use columns for synonyms (canonical,synonym), "
            + "business_terms (term,entity,column_name,value), or abbreviations (abbreviation,entity,value).");
  }

  public Map<String, Object> preview(List<Map<String, String>> rows, String importType) {
    String kind = importType != null && !importType.isBlank() ? importType : detectType(rows);
    return switch (kind) {
      case "metadata" -> metadataImport.preview(rows);
      case "synonyms" -> previewSynonyms(rows);
      case "business_terms" -> previewBusinessTerms(rows);
      case "abbreviations" -> previewAbbreviations(rows);
      default -> throw new ValidationFailed("Unsupported import type: " + kind);
    };
  }

  @Transactional
  public Map<String, Object> commit(List<Map<String, String>> rows, String importType) {
    String kind = importType != null && !importType.isBlank() ? importType : detectType(rows);
    return switch (kind) {
      case "metadata" -> metadataImport.commit(rows);
      case "synonyms" -> commitSynonyms(rows);
      case "business_terms" -> commitBusinessTerms(rows);
      case "abbreviations" -> commitAbbreviations(rows);
      default -> throw new ValidationFailed("Unsupported import type: " + kind);
    };
  }

  private Map<String, Object> previewSynonyms(List<Map<String, String>> rows) {
    List<Map<String, Object>> changes = new ArrayList<>();
    List<Map<String, Object>> unmatched = new ArrayList<>();
    for (int i = 0; i < rows.size(); i++) {
      Map<String, String> row = rows.get(i);
      String canonical = row.getOrDefault("canonical", "").trim();
      if (canonical.isBlank()) {
        unmatched.add(Map.of("row", i + 1, "reason", "missing canonical"));
        continue;
      }
      List<String> values = synonymValues(row);
      if (values.isEmpty()) {
        unmatched.add(Map.of("row", i + 1, "reason", "missing synonym(s)"));
        continue;
      }
      for (String syn : values) {
        changes.add(
            Map.of(
                "entity_type", "synonym",
                "label", canonical,
                "field", "synonym",
                "current", "",
                "proposed", syn));
      }
    }
    return result("synonyms", rows.size() - unmatched.size(), unmatched, changes);
  }

  private Map<String, Object> previewBusinessTerms(List<Map<String, String>> rows) {
    List<Map<String, Object>> changes = new ArrayList<>();
    List<Map<String, Object>> unmatched = new ArrayList<>();
    for (int i = 0; i < rows.size(); i++) {
      Map<String, String> row = rows.get(i);
      String term = row.getOrDefault("term", "").trim();
      String entity = row.getOrDefault("entity", "").trim();
      String columnName = row.getOrDefault("column_name", row.getOrDefault("column", "")).trim();
      String value = row.getOrDefault("value", "").trim();
      if (term.isBlank() || entity.isBlank() || columnName.isBlank() || value.isBlank()) {
        unmatched.add(
            Map.of("row", i + 1, "reason", "term, entity, column_name, and value are required"));
        continue;
      }
      changes.add(
          Map.of(
              "entity_type", "business_term",
              "label", term,
              "field", "binding",
              "current", "",
              "proposed", entity + "." + columnName + " = " + value));
    }
    return result("business_terms", rows.size() - unmatched.size(), unmatched, changes);
  }

  private Map<String, Object> previewAbbreviations(List<Map<String, String>> rows) {
    List<Map<String, Object>> changes = new ArrayList<>();
    List<Map<String, Object>> unmatched = new ArrayList<>();
    for (int i = 0; i < rows.size(); i++) {
      Map<String, String> row = rows.get(i);
      String abbrev = row.getOrDefault("abbreviation", row.getOrDefault("abbrev", "")).trim();
      String entity = row.getOrDefault("entity", row.getOrDefault("canonical", "")).trim();
      String value = row.getOrDefault("value", row.getOrDefault("canonical", "")).trim();
      if (abbrev.isBlank() || entity.isBlank() || value.isBlank()) {
        unmatched.add(Map.of("row", i + 1, "reason", "abbreviation, entity, and value are required"));
        continue;
      }
      changes.add(
          Map.of(
              "entity_type", "abbreviation",
              "label", abbrev,
              "field", "binding",
              "current", "",
              "proposed", entity + " = " + value));
    }
    return result("abbreviations", rows.size() - unmatched.size(), unmatched, changes);
  }

  @Transactional
  protected Map<String, Object> commitSynonyms(List<Map<String, String>> rows) {
    Map<String, Object> preview = previewSynonyms(rows);
    int synonymsAdded = 0;
    int applied = 0;
    for (Map<String, String> row : rows) {
      String canonical = row.getOrDefault("canonical", "").trim();
      if (canonical.isBlank()) continue;
      List<String> values = synonymValues(row);
      if (values.isEmpty()) continue;
      GlossaryTerm term = resolveCanonical(canonical);
      Set<String> existing =
          new HashSet<>(
              synonyms.findByTermId(term.getId()).stream()
                  .map(s -> s.getSynonym().toLowerCase(Locale.ROOT))
                  .toList());
      for (String syn : values) {
        if (existing.contains(syn.toLowerCase(Locale.ROOT))) continue;
        Synonym s = new Synonym();
        s.setTermId(term.getId());
        s.setSynonym(syn);
        s.setSource("imported");
        synonyms.save(s);
        synonymsAdded++;
      }
      applied++;
    }
    Map<String, Object> out = new HashMap<>(preview);
    out.put("applied", applied);
    out.put("synonyms_added", synonymsAdded);
    return out;
  }

  @Transactional
  protected Map<String, Object> commitBusinessTerms(List<Map<String, String>> rows) {
    Map<String, Object> preview = previewBusinessTerms(rows);
    int applied = 0;
    for (Map<String, String> row : rows) {
      String term = row.getOrDefault("term", "").trim();
      String entity = row.getOrDefault("entity", "").trim();
      String columnName = row.getOrDefault("column_name", row.getOrDefault("column", "")).trim();
      String value = row.getOrDefault("value", "").trim();
      if (term.isBlank() || entity.isBlank() || columnName.isBlank() || value.isBlank()) continue;
      BusinessTerm bt = new BusinessTerm();
      bt.setTerm(term);
      bt.setEntity(entity);
      bt.setColumnName(columnName);
      bt.setValue(value);
      bt.setTableId(resolveTableId(entity));
      bt.setSource("imported");
      bt.setStatus("approved");
      businessTerms.save(bt);
      applied++;
    }
    Map<String, Object> out = new HashMap<>(preview);
    out.put("applied", applied);
    return out;
  }

  @Transactional
  protected Map<String, Object> commitAbbreviations(List<Map<String, String>> rows) {
    Map<String, Object> preview = previewAbbreviations(rows);
    int applied = 0;
    for (Map<String, String> row : rows) {
      String abbrev = row.getOrDefault("abbreviation", row.getOrDefault("abbrev", "")).trim();
      String entity = row.getOrDefault("entity", row.getOrDefault("canonical", "")).trim();
      String value = row.getOrDefault("value", row.getOrDefault("canonical", "")).trim();
      if (abbrev.isBlank() || entity.isBlank() || value.isBlank()) continue;
      Abbreviation a = new Abbreviation();
      a.setAbbreviation(abbrev);
      a.setEntity(entity);
      a.setValue(value);
      String desc = row.getOrDefault("description", "").trim();
      if (!desc.isBlank()) a.setDescription(desc);
      a.setSource("imported");
      a.setStatus("approved");
      abbreviations.save(a);
      applied++;
    }
    Map<String, Object> out = new HashMap<>(preview);
    out.put("applied", applied);
    return out;
  }

  private GlossaryTerm resolveCanonical(String canonical) {
    return glossary
        .findByTermIgnoreCase(canonical)
        .orElseGet(
            () -> {
              GlossaryTerm term = new GlossaryTerm();
              term.setTerm(canonical);
              term.setDefinition(canonical);
              term.setSource("imported");
              term.setStatus("approved");
              glossary.save(term);
              return term;
            });
  }

  private String resolveTableId(String entity) {
    if (!entity.contains(".")) return null;
    String[] parts = entity.split("\\.", 2);
    String dbName = parts[0];
    String tableName = parts[1];
    return databases.findAll().stream()
        .filter(d -> d.getName().equalsIgnoreCase(dbName))
        .flatMap(d -> tables.findByDatabaseIdAndIsActiveTrue(d.getId()).stream())
        .filter(t -> t.getName().equalsIgnoreCase(tableName))
        .map(com.datalens.model.entity.CatalogTable::getId)
        .findFirst()
        .orElse(null);
  }

  private static List<String> synonymValues(Map<String, String> row) {
    List<String> values = new ArrayList<>();
    if (row.get("synonym") != null && !row.get("synonym").isBlank()) {
      values.add(row.get("synonym").trim());
    }
    if (row.get("synonyms") != null && !row.get("synonyms").isBlank()) {
      for (String part : row.get("synonyms").split(",")) {
        if (!part.isBlank()) values.add(part.trim());
      }
    }
    return values;
  }

  private static Map<String, Object> result(
      String importType, int matched, List<Map<String, Object>> unmatched, List<Map<String, Object>> changes) {
    Map<String, Object> out = new HashMap<>();
    out.put("import_type", importType);
    out.put("matched_rows", matched);
    out.put("unmatched", unmatched);
    out.put("changes", changes);
    return out;
  }
}
