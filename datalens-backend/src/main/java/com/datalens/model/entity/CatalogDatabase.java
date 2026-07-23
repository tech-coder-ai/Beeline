package com.datalens.model.entity;

import com.datalens.core.persistence.BaseEntity;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.OneToMany;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import lombok.Getter;
import lombok.Setter;

@Entity
@Table(name = "catalog_databases")
@Getter
@Setter
public class CatalogDatabase extends BaseEntity {
  @Column(name = "connector_id", length = 64)
  private String connectorId;
  private String name;
  private String description;
  @Column(name = "table_count")
  private Integer tableCount = 0;
  @Column(name = "last_synced_at")
  private Instant lastSyncedAt;
  @OneToMany(mappedBy = "database")
  private List<CatalogTable> tables = new ArrayList<>();
}
