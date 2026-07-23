package com.datalens.model.entity;

import com.datalens.core.persistence.BaseEntity;
import com.datalens.core.persistence.JsonAttributeConverter;
import jakarta.persistence.*;
import java.time.Instant;
import lombok.Getter; import lombok.Setter;

@Entity
@Table(name = "metadata_versions")
@Getter @Setter
public class MetadataVersion extends BaseEntity {
  @Column(name = "entity_type")
  private String entityType;
  @Column(name = "entity_id")
  private String entityId;
  private String field;
  @Column(name = "old_value")
  private String oldValue;
  @Column(name = "new_value")
  private String newValue;
  private Integer version;
  @Column(name = "changed_by")
  private String changedBy;
  @Column(name = "change_source")
  private String changeSource;
  @Column(name = "approval_id")
  private String approvalId;
}
