package com.datalens.service;

import com.datalens.config.DataLensSettings;
import com.datalens.core.exception.NotFound;
import com.datalens.llm.LlmPrompts;
import com.datalens.llm.LlmProviderRegistry;
import com.datalens.model.entity.ApprovalItem;
import com.datalens.model.entity.CatalogColumn;
import com.datalens.model.entity.CatalogDatabase;
import com.datalens.model.entity.CatalogTable;
import com.datalens.model.repository.ApprovalItemRepository;
import com.datalens.model.repository.CatalogColumnRepository;
import com.datalens.model.repository.CatalogDatabaseRepository;
import com.datalens.model.repository.CatalogTableRepository;
import com.datalens.schema.api.TableEnrichRequest;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class EnrichmentService {
  private final DataLensSettings settings;
  private final CatalogTableRepository tables;
  private final CatalogColumnRepository columns;
  private final CatalogDatabaseRepository databases;
  private final ApprovalItemRepository approvals;
  private final LlmProviderRegistry llm;
  private final ObjectMapper mapper;
  private final MetadataSyncService syncService;

  public EnrichmentService(
      DataLensSettings settings,
      CatalogTableRepository tables,
      CatalogColumnRepository columns,
      CatalogDatabaseRepository databases,
      ApprovalItemRepository approvals,
      LlmProviderRegistry llm,
      ObjectMapper mapper,
      MetadataSyncService syncService) {
    this.settings = settings;
    this.tables = tables;
    this.columns = columns;
    this.databases = databases;
    this.approvals = approvals;
    this.llm = llm;
    this.mapper = mapper;
    this.syncService = syncService;
  }

  @Transactional
  public Map<String, Object> enrich(List<String> tableIds, Integer batchSizeOverride) {
    if (!Boolean.TRUE.equals(settings.get("enrichment.enabled", true))) {
      return Map.of("enriched", 0, "proposals", 0, "skipped", "enrichment disabled");
    }

    int batchSize =
        batchSizeOverride != null
            ? batchSizeOverride
            : ((Number) settings.get("enrichment.batch_size", 10)).intValue();

    List<CatalogTable> target;
    if (tableIds != null && !tableIds.isEmpty()) {
      target = tables.findAllById(tableIds).stream().filter(t -> !Boolean.FALSE.equals(t.getIsActive())).toList();
    } else {
      var stream =
          tables.findByIsActiveTrueOrderByUsageCountDescNameAsc().stream()
              .filter(t -> t.getDescription() == null || t.getDescription().isBlank());
      target = batchSize > 0 ? stream.limit(batchSize).toList() : stream.toList();
    }

    int proposals = 0;
    for (CatalogTable table : target) {
      try {
        proposals += enrichOne(table);
      } catch (Exception ignored) {
      }
    }

    Map<String, Object> result = new LinkedHashMap<>();
    result.put("enriched", target.size());
    result.put("proposals", proposals);
    result.put("batch_size", batchSize);
    result.put(
        "note",
        tableIds == null || tableIds.isEmpty()
            ? "Bulk enrich processes tables missing descriptions per enrichment.batch_size (set 0 for all)."
            : "Enriched selected tables including columns.");
    return result;
  }

  @Transactional
  public Map<String, Object> enrichTable(String tableId, TableEnrichRequest request) throws Exception {
    if (!Boolean.TRUE.equals(settings.get("enrichment.enabled", true))) {
      return Map.of("enriched", 0, "proposals", 0, "skipped", "enrichment disabled");
    }

    CatalogTable table =
        tables.findById(tableId).orElseThrow(() -> new NotFound("Table not found"));

    if (request != null) {
      if (request.description() != null && !request.description().isBlank()) {
        table.setDescription(request.description().trim());
      }
      if (request.tags() != null && !request.tags().isEmpty()) {
        table.setTags(request.tags());
      }
      tables.save(table);
    }

    Map<String, Object> rowRefresh = Map.of();
    boolean shouldRefresh =
        request == null
            || request.refreshRowCount() == null
            || Boolean.TRUE.equals(request.refreshRowCount());
    if (shouldRefresh && table.getRowCount() == null) {
      try {
        rowRefresh = syncService.refreshTableStats(tableId);
        table = tables.findById(tableId).orElseThrow(() -> new NotFound("Table not found"));
      } catch (Exception ignored) {
        rowRefresh = Map.of("row_count_refresh", "failed");
      }
    }

    Map<String, Object> userContext = buildUserContext(table, request);
    int proposals = enrichOne(table, userContext);

    Map<String, Object> result = new LinkedHashMap<>();
    result.put("enriched", 1);
    result.put("proposals", proposals);
    result.put("table_id", tableId);
    result.put("row_count", table.getRowCount());
    if (!rowRefresh.isEmpty()) result.put("row_count_refresh", rowRefresh);
    result.put(
        "note",
        "AI proposals were queued for approval. Review them in the Approvals tab.");
    return result;
  }

  private Map<String, Object> buildUserContext(CatalogTable table, TableEnrichRequest request) {
    Map<String, Object> ctx = new LinkedHashMap<>();
    if (table.getDescription() != null && !table.getDescription().isBlank()) {
      ctx.put("description", table.getDescription());
    }
    if (table.getTags() instanceof List<?> tags && !tags.isEmpty()) {
      ctx.put("tags", tags);
    }
    if (request != null && request.glossaryHints() != null && !request.glossaryHints().isEmpty()) {
      List<Map<String, String>> hints = new ArrayList<>();
      for (TableEnrichRequest.GlossaryHint hint : request.glossaryHints()) {
        if (hint.term() == null || hint.term().isBlank()) continue;
        Map<String, String> row = new LinkedHashMap<>();
        row.put("term", hint.term().trim());
        if (hint.definition() != null) row.put("definition", hint.definition().trim());
        hints.add(row);
      }
      if (!hints.isEmpty()) ctx.put("glossary_hints", hints);
    }
    return ctx;
  }

  private int enrichOne(CatalogTable table) throws Exception {
    return enrichOne(table, Map.of());
  }

  private int enrichOne(CatalogTable table, Map<String, Object> userContext) throws Exception {
    CatalogDatabase database =
        databases.findById(table.getDatabaseId()).orElse(null);
    String dbName = database != null ? database.getName() : "";
    String label = dbName + "." + table.getName();

    List<CatalogColumn> tableColumns = columns.findByTableIdOrderByPositionAsc(table.getId());
    List<Map<String, Object>> columnPayload = new ArrayList<>();
    for (CatalogColumn col : tableColumns) {
      Map<String, Object> colMap = new LinkedHashMap<>();
      colMap.put("name", col.getName());
      colMap.put("data_type", col.getDataType());
      colMap.put("comment", col.getTechnicalComment());
      if (col.getSampleValues() instanceof List<?> samples) {
        colMap.put("sample_values", samples.stream().limit(5).map(String::valueOf).toList());
      }
      if (col.getTopValues() instanceof List<?> top) {
        colMap.put("top_values", top.stream().limit(3).map(String::valueOf).toList());
      }
      colMap.put("null_percentage", col.getNullPercentage());
      colMap.put("distinct_count", col.getDistinctCount());
      columnPayload.add(colMap);
    }

    Map<String, Object> payload = new LinkedHashMap<>();
    payload.put("table", label);
    payload.put("technical_comment", table.getTechnicalComment());
    payload.put("row_count", table.getRowCount());
    payload.put("partition_columns", table.getPartitionColumns());
    payload.put("columns", columnPayload);
    if (!userContext.isEmpty()) payload.put("user_context", userContext);

    Map<String, Object> parsed =
        llm.completeJson(LlmPrompts.ENRICHMENT_SYSTEM, mapper.writeValueAsString(payload));
    if (parsed.isEmpty()) return 0;

    double confidence = ((Number) parsed.getOrDefault("confidence", 0.5)).doubleValue();
    String rationale = String.valueOf(parsed.getOrDefault("rationale", ""));
    int count = 0;

    if (parsed.get("table_description") != null && !String.valueOf(parsed.get("table_description")).isBlank()) {
      count += saveApproval(
          "table_description", table.getId(), label, "description", table.getDescription(),
          String.valueOf(parsed.get("table_description")), null, confidence, rationale);
    }
    if (parsed.get("table_tags") != null) {
      count +=
          saveApproval(
              "tag",
              table.getId(),
              label,
              "tags",
              table.getTags() != null ? mapper.writeValueAsString(table.getTags()) : "[]",
              mapper.writeValueAsString(parsed.get("table_tags")),
              null,
              confidence,
              rationale);
    }
    if (parsed.get("classification") != null && !String.valueOf(parsed.get("classification")).isBlank()) {
      count +=
          saveApproval(
              "classification",
              table.getId(),
              label,
              "classification",
              table.getClassification(),
              String.valueOf(parsed.get("classification")),
              null,
              confidence,
              rationale);
    }

    Map<String, CatalogColumn> columnsByName = new HashMap<>();
    for (CatalogColumn col : tableColumns) columnsByName.put(col.getName(), col);

    if (parsed.get("columns") instanceof List<?> colProposals) {
      for (Object raw : colProposals) {
        if (!(raw instanceof Map<?, ?> colProposal)) continue;
        String colName = String.valueOf(colProposal.get("name"));
        CatalogColumn col = columnsByName.get(colName);
        if (col == null) continue;
        String colLabel = label + "." + col.getName();
        double colConf =
            colProposal.get("confidence") instanceof Number n ? n.doubleValue() : confidence;
        Object description = colProposal.get("description");
        if (description == null || String.valueOf(description).isBlank()) continue;
        Map<String, Object> proposedPayload = new LinkedHashMap<>();
        if (colProposal.get("semantic_type") != null) {
          proposedPayload.put("semantic_type", colProposal.get("semantic_type"));
        }
        proposedPayload.put("is_pii", Boolean.TRUE.equals(colProposal.get("is_pii")));
        if (colProposal.get("tags") != null) proposedPayload.put("tags", colProposal.get("tags"));
        count +=
            saveApproval(
                "column_description",
                col.getId(),
                colLabel,
                "description",
                col.getDescription(),
                String.valueOf(description),
                proposedPayload,
                colConf,
                rationale);
      }
    }

    if (parsed.get("glossary_suggestions") instanceof List<?> terms) {
      for (Object raw : terms) {
        if (!(raw instanceof Map<?, ?> term)) continue;
        if (term.get("term") == null || term.get("definition") == null) continue;
        Map<String, Object> proposedPayload = new LinkedHashMap<>();
        if (term.get("synonyms") != null) proposedPayload.put("synonyms", term.get("synonyms"));
        count +=
            saveApproval(
                "glossary_term",
                table.getId(),
                String.valueOf(term.get("term")),
                "glossary",
                null,
                String.valueOf(term.get("definition")),
                proposedPayload,
                confidence,
                "Suggested while documenting " + label);
      }
    }
    return count;
  }

  private int saveApproval(
      String entityType,
      String entityId,
      String entityLabel,
      String field,
      String currentValue,
      String proposedValue,
      Map<String, Object> proposedPayload,
      double confidence,
      String rationale) {
    ApprovalItem item = new ApprovalItem();
    item.setEntityType(entityType);
    item.setEntityId(entityId);
    item.setEntityLabel(entityLabel);
    item.setField(field);
    item.setCurrentValue(currentValue);
    item.setProposedValue(proposedValue);
    item.setProposedPayload(proposedPayload);
    item.setSource("ai");
    item.setConfidence(confidence);
    item.setRationale(rationale);
    item.setStatus("pending");
    approvals.save(item);
    return 1;
  }
}
