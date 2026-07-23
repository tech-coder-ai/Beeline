package com.datalens.service;

import com.datalens.config.DataLensSettings;
import com.datalens.connectors.AnalyticsConnector;
import com.datalens.connectors.ConnectorRegistry;
import com.datalens.connectors.HarvestedColumn;
import com.datalens.connectors.HarvestedTable;
import com.datalens.model.entity.CatalogColumn;
import com.datalens.model.entity.CatalogDatabase;
import com.datalens.model.entity.CatalogTable;
import com.datalens.model.entity.SyncRun;
import com.datalens.model.repository.CatalogColumnRepository;
import com.datalens.model.repository.CatalogDatabaseRepository;
import com.datalens.model.repository.CatalogTableRepository;
import com.datalens.model.repository.SyncRunRepository;
import java.time.Instant;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class MetadataSyncService {
  private static final Logger log = LoggerFactory.getLogger(MetadataSyncService.class);
  private final DataLensSettings settings;
  private final ConnectorRegistry connectors;
  private final CatalogDatabaseRepository databases;
  private final CatalogTableRepository tables;
  private final CatalogColumnRepository columns;
  private final SyncRunRepository syncRuns;
  private final Object lock = new Object();

  public MetadataSyncService(
      DataLensSettings settings,
      ConnectorRegistry connectors,
      CatalogDatabaseRepository databases,
      CatalogTableRepository tables,
      CatalogColumnRepository columns,
      SyncRunRepository syncRuns) {
    this.settings = settings;
    this.connectors = connectors;
    this.databases = databases;
    this.tables = tables;
    this.columns = columns;
    this.syncRuns = syncRuns;
  }

  @Async
  public void syncAsync(String connectorId, String mode) {
    try {
      sync(connectorId, mode);
    } catch (Exception e) {
      log.error("metadata sync failed", e);
    }
  }

  @Transactional
  public SyncRun sync(String connectorId, String mode) throws Exception {
    synchronized (lock) {
      AnalyticsConnector connector = connectors.get(connectorId);
      SyncRun run = new SyncRun();
      run.setConnectorId(connector.connectorId());
      run.setMode(mode);
      syncRuns.save(run);
      try {
        Map<String, Integer> stats = syncCatalog(connector, mode);
        run.setTablesSynced(stats.get("tables"));
        run.setColumnsSynced(stats.get("columns"));
        run.setStatus("success");
      } catch (Exception e) {
        run.setStatus("failed");
        run.setError(String.valueOf(e.getMessage()).substring(0, Math.min(2000, String.valueOf(e.getMessage()).length())));
      }
      run.setFinishedAt(Instant.now());
      return syncRuns.save(run);
    }
  }

  private Map<String, Integer> syncCatalog(AnalyticsConnector connector, String mode) throws Exception {
    int maxTables = ((Number) settings.get("metadata_sync.max_tables_per_run", 500)).intValue();
    Set<String> allowed = new HashSet<>();
    Object rawAllowed = connector.config().get("allowed_schemas");
    if (rawAllowed instanceof List<?> l) l.forEach(x -> allowed.add(String.valueOf(x)));
    Instant now = Instant.now();
    int tablesSynced = 0, columnsSynced = 0;
    for (String dbName : connector.metadataProvider().listDatabases()) {
      if (!allowed.isEmpty() && !allowed.contains(dbName)) continue;
      CatalogDatabase catalogDb =
          databases.findByConnectorIdAndName(connector.connectorId(), dbName).orElseGet(() -> {
            CatalogDatabase d = new CatalogDatabase();
            d.setConnectorId(connector.connectorId());
            d.setName(dbName);
            return databases.save(d);
          });
      List<String> tableNames = connector.metadataProvider().listTables(dbName);
      catalogDb.setTableCount(tableNames.size());
      catalogDb.setLastSyncedAt(now);
      databases.save(catalogDb);
      for (String tableName : tableNames) {
        if (tablesSynced >= maxTables) break;
        HarvestedTable harvested = connector.metadataProvider().describeTable(dbName, tableName);
        CatalogTable table =
            tables.findByDatabaseIdAndName(catalogDb.getId(), tableName).orElseGet(() -> {
              CatalogTable t = new CatalogTable();
              t.setDatabaseId(catalogDb.getId());
              t.setName(tableName);
              return t;
            });
        table.setTableType(harvested.getTableType());
        table.setTechnicalComment(harvested.getComment());
        table.setOwner(harvested.getOwner());
        table.setRowCount(harvested.getRowCount());
        table.setSizeBytes(harvested.getSizeBytes());
        table.setStorageFormat(harvested.getStorageFormat());
        table.setPartitionColumns(harvested.getPartitionColumns());
        table.setLastSyncedAt(now);
        table.setIsActive(true);
        tables.save(table);
        columns.deleteByTableId(table.getId());
        for (HarvestedColumn col : harvested.getColumns()) {
          CatalogColumn c = new CatalogColumn();
          c.setTableId(table.getId());
          c.setName(col.getName());
          c.setDataType(col.getDataType());
          c.setTechnicalComment(col.getComment());
          c.setPosition(col.getPosition());
          c.setIsPartition(col.isPartition());
          columns.save(c);
          columnsSynced++;
        }
        tablesSynced++;
      }
    }
    return Map.of("tables", tablesSynced, "columns", columnsSynced);
  }

  @Scheduled(fixedDelayString = "${datalens.metadata-sync-interval-ms:3600000}", initialDelay = 30000)
  public void scheduledSync() {
    if (!Boolean.TRUE.equals(settings.get("metadata_sync.enabled", true))) return;
    syncAsync(null, "incremental");
  }
}
