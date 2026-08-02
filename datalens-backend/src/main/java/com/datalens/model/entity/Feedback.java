package com.datalens.model.entity;

import com.datalens.core.persistence.BaseEntity;
import com.datalens.core.persistence.JsonAttributeConverter;
import jakarta.persistence.*;
import java.time.Instant;
import lombok.Getter; import lombok.Setter;

@Entity
@Table(name = "feedback")
@Getter @Setter
public class Feedback extends BaseEntity {
  @Column(name = "execution_id")
  private String executionId;
  @Column(name = "message_id")
  private String messageId;
  @Column(name = "user_id", nullable = false)
  private String userId = "default";
  private String rating;
  private String category;
  private String comment;
  @Column(name = "corrected_sql")
  private String correctedSql;
  @Column(nullable = false)
  private String status = "open";
  private Double learning;
}
