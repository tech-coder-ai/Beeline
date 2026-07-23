package com.datalens.model.entity;

import com.datalens.core.persistence.BaseEntity;
import com.datalens.core.persistence.JsonAttributeConverter;
import jakarta.persistence.*;
import java.time.Instant;
import lombok.Getter; import lombok.Setter;

@Entity
@Table(name = "audit_logs")
@Getter @Setter
public class AuditLog extends BaseEntity {
  @Column(name = "user_id")
  private String userId;
  private String action;
  @Column(name = "entity_type")
  private String entityType;
  @Column(name = "entity_id")
  private String entityId;
  @Convert(converter = JsonAttributeConverter.class)
  @Column(name = "detail")
  private Object detail;
  private String severity;
}
