package com.datalens.model.entity;

import com.datalens.core.persistence.BaseEntity;
import com.datalens.core.persistence.JsonAttributeConverter;
import jakarta.persistence.*;
import java.time.Instant;
import lombok.Getter; import lombok.Setter;

@Entity
@Table(name = "sync_runs")
@Getter @Setter
public class SyncRun extends BaseEntity {
  @Column(name = "connector_id")
  private String connectorId;
  private String mode;
  private String status;
  @Column(name = "tables_synced")
  private Integer tablesSynced;
  @Column(name = "columns_synced")
  private Integer columnsSynced;
  private String error;
  @Column(name = "finished_at")
  private Instant finishedAt;
}
