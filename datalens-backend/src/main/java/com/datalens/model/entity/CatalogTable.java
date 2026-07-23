package com.datalens.model.entity;

import com.datalens.core.persistence.BaseEntity;
import com.datalens.core.persistence.JsonAttributeConverter;
import jakarta.persistence.Column;
import jakarta.persistence.Convert;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.OneToMany;
import jakarta.persistence.OrderBy;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import lombok.Getter;
import lombok.Setter;

@Entity
@Table(name = "catalog_tables")
@Getter
@Setter
public class CatalogTable extends BaseEntity {
  @Column(name = "database_id")
  private String databaseId;
  private String name;
  @Column(name = "table_type")
  private String tableType = "TABLE";
  private String description;
  @Column(name = "technical_comment")
  private String technicalComment;
  private String owner;
  private String steward;
  @Convert(converter = JsonAttributeConverter.class)
  private Object tags;
  private String classification;
  @Column(name = "row_count")
  private Integer rowCount;
  @Column(name = "size_bytes")
  private Long sizeBytes;
  @Column(name = "storage_format")
  private String storageFormat;
  private String compression;
  @Convert(converter = JsonAttributeConverter.class)
  @Column(name = "partition_columns")
  private Object partitionColumns;
  @Column(name = "last_analyzed_at")
  private Instant lastAnalyzedAt;
  @Column(name = "last_synced_at")
  private Instant lastSyncedAt;
  @Column(name = "usage_count")
  private Integer usageCount = 0;
  @Column(name = "is_active")
  private Boolean isActive = true;
  @ManyToOne(fetch = FetchType.LAZY)
  @JoinColumn(name = "database_id", insertable = false, updatable = false)
  private CatalogDatabase database;
  @OneToMany(mappedBy = "table")
  @OrderBy("position ASC")
  private List<CatalogColumn> columns = new ArrayList<>();
}
