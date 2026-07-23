package com.datalens.service;

import com.datalens.core.exception.NotFound;
import com.datalens.core.exception.ValidationFailed;
import com.datalens.model.entity.ApprovalItem;
import com.datalens.model.entity.CatalogColumn;
import com.datalens.model.entity.CatalogTable;
import com.datalens.model.entity.GlossaryTerm;
import com.datalens.model.entity.MetadataVersion;
import com.datalens.model.entity.Synonym;
import com.datalens.model.repository.ApprovalItemRepository;
import com.datalens.model.repository.CatalogColumnRepository;
import com.datalens.model.repository.CatalogTableRepository;
import com.datalens.model.repository.GlossaryTermRepository;
import com.datalens.model.repository.MetadataVersionRepository;
import com.datalens.model.repository.SynonymRepository;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ApprovalService {
  private final ApprovalItemRepository approvals;
  private final CatalogTableRepository tables;
  private final CatalogColumnRepository columns;
  private final GlossaryTermRepository glossary;
  private final SynonymRepository synonyms;
  private final MetadataVersionRepository versions;
  private final AuditService audit;
  private final ObjectMapper mapper;

  public ApprovalService(
      ApprovalItemRepository approvals,
      CatalogTableRepository tables,
      CatalogColumnRepository columns,
      GlossaryTermRepository glossary,
      SynonymRepository synonyms,
      MetadataVersionRepository versions,
      AuditService audit,
      ObjectMapper mapper) {
    this.approvals = approvals;
    this.tables = tables;
    this.columns = columns;
    this.glossary = glossary;
    this.synonyms = synonyms;
    this.versions = versions;
    this.audit = audit;
    this.mapper = mapper;
  }

  public List<ApprovalItem> listPending(String entityType, String status) {
    if (entityType == null || entityType.isBlank()) {
      return approvals.findByStatusOrderByCreatedAtDesc(status != null ? status : "pending");
    }
    return approvals.findByEntityTypeAndStatusOrderByCreatedAtDesc(entityType, status != null ? status : "pending");
  }

  public Map<String, Long> counts() {
    return approvals.countPendingByEntityType().stream()
        .collect(java.util.stream.Collectors.toMap(r -> (String) r[0], r -> (Long) r[1]));
  }

  @Transactional
  public ApprovalItem decide(String itemId, String action, String editedValue, String note) {
    ApprovalItem item = approvals.findById(itemId).orElseThrow(() -> new NotFound("Approval item not found"));
    if (!"pending".equals(item.getStatus())) throw new ValidationFailed("Item already " + item.getStatus());
    item.setReviewedBy("admin");
    item.setReviewedAt(Instant.now());
    item.setReviewNote(note);
    if ("reject".equals(action)) item.setStatus("rejected");
    else if ("approve".equals(action) || "edit".equals(action)) {
      String value = "edit".equals(action) && editedValue != null ? editedValue : item.getProposedValue();
      item.setFinalValue(value);
      item.setStatus("edit".equals(action) ? "edited" : "approved");
      apply(item, value);
    } else throw new ValidationFailed("Unknown action '" + action + "'");
    audit.audit("admin", "metadata." + item.getStatus(), item.getEntityType(), item.getEntityId(), Map.of("field", item.getField()), "info");
    return approvals.save(item);
  }

  @Transactional
  public Map<String, Integer> bulkDecide(List<String> ids, String action, String note) {
    int ok = 0, fail = 0;
    for (String id : ids) {
      try {
        decide(id, action, null, note);
        ok++;
      } catch (RuntimeException e) {
        fail++;
      }
    }
    return Map.of("succeeded", ok, "failed", fail);
  }

  public List<MetadataVersion> history(String entityType, String entityId) {
    return versions.findByEntityTypeAndEntityIdOrderByCreatedAtDesc(entityType, entityId);
  }

  @Transactional
  public void rollback(String versionId) {
    MetadataVersion v = versions.findById(versionId).orElseThrow(() -> new NotFound("Version not found"));
    writeValue(v.getEntityType(), v.getEntityId(), v.getField(), v.getOldValue());
    recordVersion(v.getEntityType(), v.getEntityId(), v.getField(), v.getNewValue(), v.getOldValue(), "rollback");
    audit.audit("admin", "metadata.rollback", v.getEntityType(), v.getEntityId(), Map.of("field", v.getField()), "info");
  }

  private void apply(ApprovalItem item, String value) {
    switch (item.getEntityType()) {
      case "table_description" -> tables.findById(item.getEntityId()).ifPresent(t -> t.setDescription(value));
      case "column_description" -> columns.findById(item.getEntityId()).ifPresent(c -> c.setDescription(value));
      case "tag" -> tables.findById(item.getEntityId()).ifPresent(t -> t.setTags(parseTags(value)));
      case "classification" -> tables.findById(item.getEntityId()).ifPresent(t -> t.setClassification(value));
      case "glossary_term" -> {
        GlossaryTerm term = new GlossaryTerm();
        term.setTerm(item.getEntityLabel());
        term.setDefinition(value);
        term.setSource("ai");
        term.setStatus("approved");
        glossary.save(term);
      }
      default -> throw new ValidationFailed("Unsupported entity type '" + item.getEntityType() + "'");
    }
    recordVersion(item.getEntityType(), item.getEntityId(), item.getField(), item.getCurrentValue(), value, "approval");
  }

  private void writeValue(String entityType, String entityId, String field, String value) {
    if ("table_description".equals(entityType) || "classification".equals(entityType)) {
      CatalogTable t = tables.findById(entityId).orElseThrow(() -> new NotFound("Table not found"));
      if ("tags".equals(field)) t.setTags(parseTags(value));
      else t.setDescription(value);
    } else if ("column_description".equals(entityType)) {
      columns.findById(entityId).ifPresent(c -> c.setDescription(value));
    }
  }

  private void recordVersion(
      String entityType, String entityId, String field, String oldValue, String newValue, String source) {
    MetadataVersion v = new MetadataVersion();
    v.setEntityType(entityType);
    v.setEntityId(entityId);
    v.setField(field);
    v.setOldValue(oldValue);
    v.setNewValue(newValue);
    v.setVersion((int) versions.count() + 1);
    v.setChangedBy("admin");
    v.setChangeSource(source);
    versions.save(v);
  }

  private Object parseTags(String value) {
    if (value != null && value.startsWith("[")) {
      try {
        return mapper.readValue(value, List.class);
      } catch (Exception ignored) {
      }
    }
    return List.of(value);
  }
}
