package com.datalens.model.entity;

import com.datalens.core.persistence.BaseEntity;
import com.datalens.core.persistence.JsonAttributeConverter;
import jakarta.persistence.*;
import java.time.Instant;
import lombok.Getter; import lombok.Setter;

@Entity
@Table(name = "approval_items")
@Getter @Setter
public class ApprovalItem extends BaseEntity {
  @Column(name = "entity_type")
  private String entityType;
  @Column(name = "entity_id")
  private String entityId;
  @Column(name = "entity_label")
  private String entityLabel;
  private String field;
  @Column(name = "current_value")
  private String currentValue;
  @Column(name = "proposed_value")
  private String proposedValue;
  @Convert(converter = JsonAttributeConverter.class)
  @Column(name = "proposed_payload")
  private Object proposedPayload;
  private String source;
  @Column(name = "Double")
  private String confidence;
  private String rationale;
  private String status;
  @Column(name = "reviewed_by")
  private String reviewedBy;
  @Column(name = "reviewed_at")
  private Instant reviewedAt;
  @Column(name = "review_note")
  private String reviewNote;
  @Column(name = "final_value")
  private String finalValue;
}
