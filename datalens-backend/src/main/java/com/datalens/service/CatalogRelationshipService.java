package com.datalens.service;

import com.datalens.core.exception.NotFound;
import com.datalens.core.exception.ValidationFailed;
import com.datalens.model.entity.CatalogColumn;
import com.datalens.model.entity.CatalogDatabase;
import com.datalens.model.entity.CatalogRelationship;
import com.datalens.model.entity.CatalogTable;
import com.datalens.model.repository.CatalogColumnRepository;
import com.datalens.model.repository.CatalogDatabaseRepository;
import com.datalens.model.repository.CatalogRelationshipRepository;
import com.datalens.model.repository.CatalogTableRepository;
import com.datalens.schema.api.RelationshipIn;
import com.datalens.schema.api.RelationshipOut;
import com.datalens.schema.api.RelationshipUpdate;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CatalogRelationshipService {
  private static final Set<String> CARDINALITIES =
      Set.of("many_to_one", "one_to_many", "one_to_one", "many_to_many");
  private static final Set<String> JOIN_TYPES = Set.of("inner", "left", "right", "full");

  private final CatalogRelationshipRepository relationships;
  private final CatalogTableRepository tables;
  private final CatalogColumnRepository columns;
  private final CatalogDatabaseRepository databases;

  public CatalogRelationshipService(
      CatalogRelationshipRepository relationships,
      CatalogTableRepository tables,
      CatalogColumnRepository columns,
      CatalogDatabaseRepository databases) {
    this.relationships = relationships;
    this.tables = tables;
    this.columns = columns;
    this.databases = databases;
  }

  public List<RelationshipOut> listForTable(String tableId) {
    tables.findById(tableId).orElseThrow(() -> new NotFound("Table not found"));
    return relationships.findByFromTableIdOrToTableIdOrderByCreatedAtDesc(tableId, tableId).stream()
        .map(this::toOut)
        .toList();
  }

  @Transactional
  public RelationshipOut create(RelationshipIn in) {
    CatalogTable from = tables.findById(in.fromTableId()).orElseThrow(() -> new NotFound("From table not found"));
    CatalogTable to = tables.findById(in.toTableId()).orElseThrow(() -> new NotFound("To table not found"));
    List<String> fromCols = normalizeColumns(in.fromColumns(), from.getId(), "from");
    List<String> toCols = normalizeColumns(in.toColumns(), to.getId(), "to");
    if (fromCols.size() != toCols.size()) {
      throw new ValidationFailed("from_columns and to_columns must have the same length");
    }

    CatalogRelationship rel = new CatalogRelationship();
    rel.setFromTableId(from.getId());
    rel.setToTableId(to.getId());
    applyColumns(rel, fromCols, toCols);
    rel.setRelationshipType(normalizeCardinality(in.relationshipType()));
    rel.setJoinType(normalizeJoinType(in.joinType()));
    rel.setDescription(trimOrNull(in.description()));
    rel.setSource("manual");
    rel.setIsApproved(in.isApproved() == null || in.isApproved());
    return toOut(relationships.save(rel));
  }

  @Transactional
  public RelationshipOut update(String id, RelationshipUpdate update) {
    CatalogRelationship rel =
        relationships.findById(id).orElseThrow(() -> new NotFound("Relationship not found"));
    if (update.fromColumns() != null || update.toColumns() != null) {
      List<String> fromCols =
          update.fromColumns() != null
              ? normalizeColumns(update.fromColumns(), rel.getFromTableId(), "from")
              : columnList(rel.getFromColumns(), rel.getFromColumn());
      List<String> toCols =
          update.toColumns() != null
              ? normalizeColumns(update.toColumns(), rel.getToTableId(), "to")
              : columnList(rel.getToColumns(), rel.getToColumn());
      if (fromCols.size() != toCols.size()) {
        throw new ValidationFailed("from_columns and to_columns must have the same length");
      }
      applyColumns(rel, fromCols, toCols);
    }
    if (update.relationshipType() != null) rel.setRelationshipType(normalizeCardinality(update.relationshipType()));
    if (update.joinType() != null) rel.setJoinType(normalizeJoinType(update.joinType()));
    if (update.description() != null) rel.setDescription(trimOrNull(update.description()));
    if (update.isApproved() != null) rel.setIsApproved(update.isApproved());
    return toOut(relationships.save(rel));
  }

  @Transactional
  public void delete(String id) {
    if (!relationships.existsById(id)) throw new NotFound("Relationship not found");
    relationships.deleteById(id);
  }

  public String formatForPlanner(Map<String, String> tableQualifiedNames, List<CatalogRelationship> rows) {
    if (rows.isEmpty()) return "";
    StringBuilder sb = new StringBuilder();
    for (CatalogRelationship r : rows) {
      String from = tableQualifiedNames.get(r.getFromTableId());
      String to = tableQualifiedNames.get(r.getToTableId());
      if (from == null || to == null) continue;
      List<String> fromCols = columnList(r.getFromColumns(), r.getFromColumn());
      List<String> toCols = columnList(r.getToColumns(), r.getToColumn());
      String keys =
          zipKeys(from, fromCols, to, toCols).stream().collect(Collectors.joining(" AND "));
      sb.append(from)
          .append(" -> ")
          .append(to)
          .append(": ")
          .append(keys)
          .append(" [")
          .append(r.getRelationshipType() != null ? r.getRelationshipType() : "many_to_one")
          .append(", ")
          .append(r.getJoinType() != null ? r.getJoinType() : "inner")
          .append(" join");
      if (r.getDescription() != null && !r.getDescription().isBlank()) {
        sb.append("; ").append(r.getDescription().trim());
      }
      sb.append("]\n");
    }
    return sb.toString().trim();
  }

  private RelationshipOut toOut(CatalogRelationship rel) {
    CatalogTable from = tables.findById(rel.getFromTableId()).orElseThrow();
    CatalogTable to = tables.findById(rel.getToTableId()).orElseThrow();
    String fromDb = databases.findById(from.getDatabaseId()).map(CatalogDatabase::getName).orElse("");
    String toDb = databases.findById(to.getDatabaseId()).map(CatalogDatabase::getName).orElse("");
    return new RelationshipOut(
        rel.getId(),
        rel.getFromTableId(),
        from.getName(),
        fromDb,
        rel.getToTableId(),
        to.getName(),
        toDb,
        columnList(rel.getFromColumns(), rel.getFromColumn()),
        columnList(rel.getToColumns(), rel.getToColumn()),
        rel.getRelationshipType(),
        rel.getJoinType(),
        rel.getDescription(),
        rel.getSource(),
        rel.getConfidence(),
        Boolean.TRUE.equals(rel.getIsApproved()),
        rel.getCreatedAt(),
        rel.getUpdatedAt());
  }

  private List<String> normalizeColumns(List<String> raw, String tableId, String label) {
    if (raw == null || raw.isEmpty()) {
      throw new ValidationFailed(label + "_columns must not be empty");
    }
    Set<String> valid =
        columns.findByTableIdOrderByPositionAsc(tableId).stream()
            .map(CatalogColumn::getName)
            .map(n -> n.toLowerCase(Locale.ROOT))
            .collect(Collectors.toSet());
    List<String> out = new ArrayList<>();
    for (String col : raw) {
      if (col == null || col.isBlank()) continue;
      String trimmed = col.trim();
      if (!valid.contains(trimmed.toLowerCase(Locale.ROOT))) {
        throw new ValidationFailed("Unknown " + label + " column: " + trimmed);
      }
      out.add(trimmed);
    }
    if (out.isEmpty()) throw new ValidationFailed(label + "_columns must not be empty");
    return out;
  }

  private static void applyColumns(CatalogRelationship rel, List<String> fromCols, List<String> toCols) {
    rel.setFromColumns(fromCols);
    rel.setToColumns(toCols);
    rel.setFromColumn(fromCols.get(0));
    rel.setToColumn(toCols.get(0));
  }

  private static String normalizeCardinality(String value) {
    String v = value == null ? "many_to_one" : value.trim().toLowerCase(Locale.ROOT);
    if (!CARDINALITIES.contains(v)) {
      throw new ValidationFailed("relationship_type must be one of: " + CARDINALITIES);
    }
    return v;
  }

  private static String normalizeJoinType(String value) {
    String v = value == null ? "inner" : value.trim().toLowerCase(Locale.ROOT);
    if (!JOIN_TYPES.contains(v)) {
      throw new ValidationFailed("join_type must be one of: " + JOIN_TYPES);
    }
    return v;
  }

  private static String trimOrNull(String value) {
    if (value == null) return null;
    String trimmed = value.trim();
    return trimmed.isEmpty() ? null : trimmed;
  }

  @SuppressWarnings("unchecked")
  static List<String> columnList(Object jsonColumns, String fallback) {
    if (jsonColumns instanceof List<?> list && !list.isEmpty()) {
      return list.stream().map(String::valueOf).filter(s -> !s.isBlank()).toList();
    }
    return fallback != null && !fallback.isBlank() ? List.of(fallback) : List.of();
  }

  private static List<String> zipKeys(String fromTable, List<String> fromCols, String toTable, List<String> toCols) {
    List<String> keys = new ArrayList<>();
    for (int i = 0; i < fromCols.size(); i++) {
      keys.add(fromTable + "." + fromCols.get(i) + " = " + toTable + "." + toCols.get(i));
    }
    return keys;
  }
}
