package com.datalens.model.entity;

import com.datalens.core.persistence.BaseEntity;
import com.datalens.core.persistence.JsonAttributeConverter;
import jakarta.persistence.*;
import java.time.Instant;
import lombok.Getter; import lombok.Setter;

@Entity
@Table(name = "query_library")
@Getter @Setter
public class QueryLibraryEntry extends BaseEntity {
  private String question;
  @Column(name = "normalized_question")
  private String normalizedQuestion;
  private String sql;
  @Column(name = "connector_id")
  private String connectorId;
  @Convert(converter = JsonAttributeConverter.class)
  @Column(name = "tables_used")
  private Object tablesUsed;
  @Convert(converter = JsonAttributeConverter.class)
  @Column(name = "intent")
  private Object intent;
  @Convert(converter = JsonAttributeConverter.class)
  @Column(name = "execution_plan")
  private Object executionPlan;
  @Column(name = "success_count")
  private Integer successCount;
  @Column(name = "positive_feedback")
  private Integer positiveFeedback;
  @Column(name = "negative_feedback")
  private Integer negativeFeedback;
  @Column(name = "avg_execution_ms")
  private Double avgExecutionMs;
  @Column(name = "is_active")
  private Boolean isActive;
}
