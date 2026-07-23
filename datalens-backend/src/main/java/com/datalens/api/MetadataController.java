package com.datalens.api;

import com.datalens.core.exception.NotFound;
import com.datalens.model.entity.ApprovalItem;
import com.datalens.model.entity.CatalogColumn;
import com.datalens.model.entity.CatalogDatabase;
import com.datalens.model.entity.CatalogTable;
import com.datalens.model.entity.GlossaryTerm;
import com.datalens.model.entity.MetadataVersion;
import com.datalens.model.entity.Synonym;
import com.datalens.model.repository.BusinessMetricRepository;
import com.datalens.model.repository.CatalogColumnRepository;
import com.datalens.model.repository.CatalogDatabaseRepository;
import com.datalens.model.repository.CatalogTableRepository;
import com.datalens.model.repository.GlossaryTermRepository;
import com.datalens.model.repository.SynonymRepository;
import com.datalens.schema.api.ApprovalDecision;
import com.datalens.schema.api.ApprovalOut;
import com.datalens.schema.api.BulkApprovalDecision;
import com.datalens.schema.api.ColumnOut;
import com.datalens.schema.api.ColumnUpdate;
import com.datalens.schema.api.GlossaryTermIn;
import com.datalens.schema.api.GlossaryTermOut;
import com.datalens.schema.api.TableDetailOut;
import com.datalens.schema.api.TableOut;
import com.datalens.schema.api.TableUpdate;
import com.datalens.service.ApprovalService;
import com.datalens.service.AuditService;
import com.datalens.service.ImportExportService;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping("${datalens.api-prefix}")
public class MetadataController {
  private final CatalogDatabaseRepository databases;
  private final CatalogTableRepository tables;
  private final CatalogColumnRepository columns;
  private final ApprovalService approvals;
  private final AuditService audit;
  private final ImportExportService importExport;
  private final GlossaryTermRepository glossary;
  private final SynonymRepository synonyms;
  private final BusinessMetricRepository metrics;

  public MetadataController(
      CatalogDatabaseRepository databases,
      CatalogTableRepository tables,
      CatalogColumnRepository columns,
      ApprovalService approvals,
      AuditService audit,
      ImportExportService importExport,
      GlossaryTermRepository glossary,
      SynonymRepository synonyms,
      BusinessMetricRepository metrics) {
    this.databases = databases;
    this.tables = tables;
    this.columns = columns;
    this.approvals = approvals;
    this.audit = audit;
    this.importExport = importExport;
    this.glossary = glossary;
    this.synonyms = synonyms;
    this.metrics = metrics;
  }

  @GetMapping("/metadata/databases")
  public List<Map<String, Object>> listDatabases() {
    List<Map<String, Object>> out = new ArrayList<>();
    for (CatalogDatabase d : databases.findAll()) {
      long count = tables.findByDatabaseIdAndIsActiveTrue(d.getId()).size();
      Map<String, Object> row = new HashMap<>();
      row.put("id", d.getId());
      row.put("name", d.getName());
      row.put("connector_id", d.getConnectorId());
      row.put("table_count", count);
      row.put("last_synced_at", d.getLastSyncedAt());
      out.add(row);
    }
    return out;
  }

  @GetMapping("/metadata/tables")
  public List<TableOut> listTables(
      @RequestParam(required = false) String databaseId, @RequestParam(required = false) String search) {
    List<TableOut> out = new ArrayList<>();
    for (CatalogTable t : tables.findByIsActiveTrueOrderByUsageCountDescNameAsc()) {
      if (databaseId != null && !databaseId.equals(t.getDatabaseId())) continue;
      String dbName = databases.findById(t.getDatabaseId()).map(CatalogDatabase::getName).orElse(null);
      if (search != null
          && !t.getName().toLowerCase().contains(search.toLowerCase())
          && (t.getDescription() == null || !t.getDescription().toLowerCase().contains(search.toLowerCase()))) {
        continue;
      }
      out.add(toTableOut(t, dbName, columns.findByTableIdOrderByPositionAsc(t.getId()).size()));
    }
    return out;
  }

  @GetMapping("/metadata/tables/{tableId}")
  public TableDetailOut getTable(@PathVariable String tableId) {
    CatalogTable table = tables.findById(tableId).orElseThrow(() -> new NotFound("Table not found"));
    String dbName = databases.findById(table.getDatabaseId()).map(CatalogDatabase::getName).orElse(null);
    List<ColumnOut> cols =
        columns.findByTableIdOrderByPositionAsc(table.getId()).stream().map(this::toColumnOut).toList();
    return new TableDetailOut(
        table.getId(),
        table.getName(),
        table.getTableType(),
        table.getDescription(),
        table.getOwner(),
        table.getSteward(),
        table.getTags(),
        table.getClassification(),
        table.getRowCount(),
        table.getSizeBytes(),
        table.getStorageFormat(),
        table.getPartitionColumns(),
        table.getLastSyncedAt(),
        table.getUsageCount() != null ? table.getUsageCount() : 0,
        dbName,
        cols.size(),
        cols);
  }

  @PatchMapping("/metadata/tables/{tableId}")
  public Map<String, String> updateTable(@PathVariable String tableId, @RequestBody TableUpdate update) {
    CatalogTable table = tables.findById(tableId).orElseThrow(() -> new NotFound("Table not found"));
    if (update.description() != null) table.setDescription(update.description());
    if (update.owner() != null) table.setOwner(update.owner());
    if (update.steward() != null) table.setSteward(update.steward());
    if (update.tags() != null) table.setTags(update.tags());
    if (update.classification() != null) table.setClassification(update.classification());
    tables.save(table);
    audit.audit("default", "metadata.edit", "table", tableId, Map.of(), "info");
    return Map.of("updated", tableId);
  }

  @PatchMapping("/metadata/columns/{columnId}")
  public Map<String, String> updateColumn(@PathVariable String columnId, @RequestBody ColumnUpdate update) {
    CatalogColumn column = columns.findById(columnId).orElseThrow(() -> new NotFound("Column not found"));
    if (update.description() != null) column.setDescription(update.description());
    if (update.tags() != null) column.setTags(update.tags());
    if (update.classification() != null) column.setClassification(update.classification());
    if (update.isPii() != null) column.setIsPii(update.isPii());
    columns.save(column);
    audit.audit("default", "metadata.edit", "column", columnId, Map.of(), "info");
    return Map.of("updated", columnId);
  }

  @GetMapping("/metadata/approvals")
  public List<ApprovalOut> listApprovals(
      @RequestParam(required = false) String entityType, @RequestParam(defaultValue = "pending") String status) {
    return approvals.listPending(entityType, status).stream().map(this::toApprovalOut).toList();
  }

  @GetMapping("/metadata/approvals/counts")
  public Map<String, Long> approvalCounts() {
    return approvals.counts();
  }

  @PostMapping("/metadata/approvals/{itemId}")
  public ApprovalOut decide(@PathVariable String itemId, @RequestBody ApprovalDecision decision) {
    return toApprovalOut(
        approvals.decide(itemId, decision.action(), decision.editedValue(), decision.note()));
  }

  @PostMapping("/metadata/approvals/bulk/decide")
  public Map<String, Integer> bulkDecide(@RequestBody BulkApprovalDecision decision) {
    return approvals.bulkDecide(decision.ids(), decision.action(), decision.note());
  }

  @GetMapping("/metadata/versions/{entityType}/{entityId}")
  public List<Map<String, Object>> versions(@PathVariable String entityType, @PathVariable String entityId) {
    return approvals.history(entityType, entityId).stream().map(this::versionMap).toList();
  }

  @PostMapping("/metadata/versions/{versionId}/rollback")
  public Map<String, String> rollback(@PathVariable String versionId) {
    approvals.rollback(versionId);
    return Map.of("rolled_back", versionId);
  }

  @PostMapping("/metadata/import/preview")
  public Map<String, Object> importPreview(@RequestParam("file") MultipartFile file) throws Exception {
    var rows = importExport.parse(file.getOriginalFilename() != null ? file.getOriginalFilename() : "upload.csv", file.getBytes());
    return importExport.preview(rows);
  }

  @PostMapping("/metadata/import/commit")
  public Map<String, Object> importCommit(@RequestParam("file") MultipartFile file) throws Exception {
    var rows = importExport.parse(file.getOriginalFilename() != null ? file.getOriginalFilename() : "upload.csv", file.getBytes());
    var result = importExport.commit(rows);
    audit.audit("default", "metadata.import", null, null, Map.of("rows", rows.size()), "info");
    return result;
  }

  @GetMapping("/glossary")
  public List<GlossaryTermOut> glossary(@RequestParam(required = false) String search) {
    return glossary.findAll().stream()
        .filter(t -> search == null || t.getTerm().toLowerCase().contains(search.toLowerCase()))
        .sorted(java.util.Comparator.comparing(GlossaryTerm::getTerm))
        .map(this::toGlossaryOut)
        .toList();
  }

  @PostMapping("/glossary")
  public GlossaryTermOut createGlossary(@RequestBody GlossaryTermIn in) {
    GlossaryTerm term = new GlossaryTerm();
    term.setTerm(in.term());
    term.setDefinition(in.definition());
    term.setBusinessMeaning(in.businessMeaning());
    term.setExamples(in.examples());
    term.setOwner(in.owner());
    term.setTags(in.tags());
    term.setSource("manual");
    term.setStatus("approved");
    glossary.save(term);
    for (String syn : in.synonyms()) {
      Synonym s = new Synonym();
      s.setTermId(term.getId());
      s.setSynonym(syn);
      synonyms.save(s);
    }
    return toGlossaryOut(term);
  }

  @org.springframework.web.bind.annotation.PutMapping("/glossary/{termId}")
  public GlossaryTermOut updateGlossary(@PathVariable String termId, @RequestBody GlossaryTermIn in) {
    GlossaryTerm term = glossary.findById(termId).orElseThrow(() -> new NotFound("Glossary term not found"));
    term.setTerm(in.term());
    term.setDefinition(in.definition());
    term.setBusinessMeaning(in.businessMeaning());
    term.setExamples(in.examples());
    term.setOwner(in.owner());
    term.setTags(in.tags());
    synonyms.deleteByTermId(termId);
    for (String syn : in.synonyms()) {
      Synonym s = new Synonym();
      s.setTermId(termId);
      s.setSynonym(syn);
      synonyms.save(s);
    }
    glossary.save(term);
    return toGlossaryOut(term);
  }

  @org.springframework.web.bind.annotation.DeleteMapping("/glossary/{termId}")
  public Map<String, String> deleteGlossary(@PathVariable String termId) {
    glossary.deleteById(termId);
    return Map.of("deleted", termId);
  }

  @GetMapping("/glossary/metrics")
  public List<Map<String, Object>> listMetrics() {
    return metrics.findAll().stream()
        .sorted(java.util.Comparator.comparing(com.datalens.model.entity.BusinessMetric::getName))
        .map(
            m -> {
              Map<String, Object> row = new HashMap<>();
              row.put("id", m.getId());
              row.put("name", m.getName());
              row.put("description", m.getDescription());
              row.put("expression", m.getExpression());
              row.put("table_qualified_name", m.getTableQualifiedName());
              row.put("unit", m.getUnit());
              row.put("aggregation", m.getAggregation());
              row.put("is_kpi", m.getIsKpi());
              row.put("tags", m.getTags());
              row.put("status", m.getStatus());
              return row;
            })
        .toList();
  }

  private TableOut toTableOut(CatalogTable t, String dbName, int columnCount) {
    return new TableOut(
        t.getId(),
        t.getName(),
        t.getTableType(),
        t.getDescription(),
        t.getOwner(),
        t.getSteward(),
        t.getTags(),
        t.getClassification(),
        t.getRowCount(),
        t.getSizeBytes(),
        t.getStorageFormat(),
        t.getPartitionColumns(),
        t.getLastSyncedAt(),
        t.getUsageCount() != null ? t.getUsageCount() : 0,
        dbName,
        columnCount);
  }

  private ColumnOut toColumnOut(CatalogColumn c) {
    return new ColumnOut(
        c.getId(),
        c.getName(),
        c.getPosition() != null ? c.getPosition() : 0,
        c.getDataType(),
        c.getInferredSemanticType(),
        c.getDescription(),
        c.getTags(),
        c.getClassification(),
        Boolean.TRUE.equals(c.getIsPii()),
        Boolean.TRUE.equals(c.getIsPartition()),
        c.getNullPercentage(),
        c.getDistinctCount(),
        c.getSampleValues(),
        c.getTopValues());
  }

  private ApprovalOut toApprovalOut(ApprovalItem item) {
    return new ApprovalOut(
        item.getId(),
        item.getEntityType(),
        item.getEntityId(),
        item.getEntityLabel(),
        item.getField(),
        item.getCurrentValue(),
        item.getProposedValue(),
        item.getSource(),
        item.getConfidence(),
        item.getRationale(),
        item.getStatus(),
        item.getCreatedAt());
  }

  private Map<String, Object> versionMap(MetadataVersion v) {
    Map<String, Object> m = new HashMap<>();
    m.put("id", v.getId());
    m.put("field", v.getField());
    m.put("old_value", v.getOldValue());
    m.put("new_value", v.getNewValue());
    m.put("version", v.getVersion());
    m.put("changed_by", v.getChangedBy());
    m.put("change_source", v.getChangeSource());
    m.put("created_at", v.getCreatedAt());
    return m;
  }

  private GlossaryTermOut toGlossaryOut(GlossaryTerm term) {
    List<String> syns = synonyms.findByTermId(term.getId()).stream().map(Synonym::getSynonym).toList();
    Object examples = term.getExamples() instanceof List<?> l ? l.stream().map(String::valueOf).toList() : List.of();
    Object tags = term.getTags() instanceof List<?> l ? l.stream().map(String::valueOf).toList() : List.of();
    return new GlossaryTermOut(
        term.getId(),
        term.getTerm(),
        term.getDefinition(),
        term.getBusinessMeaning(),
        (List<String>) examples,
        term.getOwner(),
        (List<String>) tags,
        syns,
        term.getStatus(),
        term.getSource(),
        term.getCreatedAt());
  }
}
