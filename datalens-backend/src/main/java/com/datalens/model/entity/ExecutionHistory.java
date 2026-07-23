package com.datalens.model.entity;

import com.datalens.core.persistence.BaseEntity;
import com.datalens.core.persistence.JsonAttributeConverter;
import jakarta.persistence.*;
import java.time.Instant;
import lombok.Getter; import lombok.Setter;

@Entity
@Table(name = "execution_history")
@Getter @Setter
public class ExecutionHistory extends BaseEntity {
  @Column(name = "session_id")
  private String sessionId;
  @Column(name = "user_id")
  private String userId;
  @Column(name = "connector_id")
  private String connectorId;
  private String prompt;
  @Column(name = "refined_prompt")
  private String refinedPrompt;
  @Convert(converter = JsonAttributeConverter.class)
  @Column(name = "intent")
  private Object intent;
  @Convert(converter = JsonAttributeConverter.class)
  @Column(name = "execution_plan")
  private Object executionPlan;
  @Column(name = "generated_sql")
  private String generatedSql;
  @Column(name = "optimized_sql")
  private String optimizedSql;
  private String status;
  @Column(name = "row_count")
  private Integer rowCount;
  @Column(name = "execution_time_ms")
  private Integer executionTimeMs;
  @Convert(converter = JsonAttributeConverter.class)
  @Column(name = "cost_estimate")
  private Object costEstimate;
  @Convert(converter = JsonAttributeConverter.class)
  @Column(name = "confidence")
  private Object confidence;
  @Convert(converter = JsonAttributeConverter.class)
  @Column(name = "warnings")
  private Object warnings;
  private String error;
  @Column(name = "llm_model")
  private String llmModel;
  @Column(name = "llm_provider")
  private String llmProvider;
  @Convert(converter = JsonAttributeConverter.class)
  @Column(name = "token_usage")
  private Object tokenUsage;
  @Convert(converter = JsonAttributeConverter.class)
  @Column(name = "tables_used")
  private Object tablesUsed;
  @Column(name = "reused_query_id")
  private String reusedQueryId;
  @Column(name = "executed_at")
  private Instant executedAt;
}
