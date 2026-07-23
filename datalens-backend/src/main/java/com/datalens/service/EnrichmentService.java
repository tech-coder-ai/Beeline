package com.datalens.service;

import com.datalens.config.DataLensSettings;
import com.datalens.llm.LlmPrompts;
import com.datalens.llm.LlmProviderRegistry;
import com.datalens.model.entity.ApprovalItem;
import com.datalens.model.entity.CatalogTable;
import com.datalens.model.repository.ApprovalItemRepository;
import com.datalens.model.repository.CatalogTableRepository;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class EnrichmentService {
  private final DataLensSettings settings;
  private final CatalogTableRepository tables;
  private final ApprovalItemRepository approvals;
  private final LlmProviderRegistry llm;
  private final ObjectMapper mapper;

  public EnrichmentService(
      DataLensSettings settings,
      CatalogTableRepository tables,
      ApprovalItemRepository approvals,
      LlmProviderRegistry llm,
      ObjectMapper mapper) {
    this.settings = settings;
    this.tables = tables;
    this.approvals = approvals;
    this.llm = llm;
    this.mapper = mapper;
  }

  @Transactional
  public Map<String, Object> enrich(List<String> tableIds) {
    if (!Boolean.TRUE.equals(settings.get("enrichment.enabled", true))) {
      return Map.of("enriched", 0, "proposals", 0, "skipped", "enrichment disabled");
    }
    List<CatalogTable> target =
        (tableIds != null && !tableIds.isEmpty())
            ? tables.findAllById(tableIds)
            : tables.findByIsActiveTrueOrderByUsageCountDescNameAsc().stream()
                .filter(t -> t.getDescription() == null)
                .limit(((Number) settings.get("enrichment.batch_size", 10)).intValue())
                .toList();
    int proposals = 0;
    for (CatalogTable table : target) {
      try {
        proposals += enrichOne(table);
      } catch (Exception ignored) {
      }
    }
    return Map.of("enriched", target.size(), "proposals", proposals);
  }

  private int enrichOne(CatalogTable table) throws Exception {
    Map<String, Object> payload = new HashMap<>();
    payload.put("table", table.getName());
    Map<String, Object> parsed = llm.completeJson(LlmPrompts.ENRICHMENT_SYSTEM, mapper.writeValueAsString(payload));
    if (parsed.isEmpty()) return 0;
    ApprovalItem item = new ApprovalItem();
    item.setEntityType("table_description");
    item.setEntityId(table.getId());
    item.setEntityLabel(table.getName());
    item.setField("description");
    item.setCurrentValue(table.getDescription());
    item.setProposedValue(String.valueOf(parsed.getOrDefault("table_description", parsed.get("description"))));
    item.setSource("ai");
    item.setConfidence(((Number) parsed.getOrDefault("confidence", 0.5)).doubleValue());
    item.setRationale(String.valueOf(parsed.getOrDefault("rationale", "")));
    approvals.save(item);
    return 1;
  }
}
