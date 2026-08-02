package com.datalens.model.entity;

import com.datalens.core.persistence.BaseEntity;
import com.datalens.core.persistence.JsonAttributeConverter;
import jakarta.persistence.*;
import java.time.Instant;
import lombok.Getter; import lombok.Setter;

@Entity
@Table(name = "saved_queries")
@Getter @Setter
public class SavedQuery extends BaseEntity {
  @Column(name = "user_id", nullable = false)
  private String userId = "default";
  private String name;
  private String description;
  private String sql;
  @Column(name = "connector_id")
  private String connectorId;
  private String prompt;
  @Convert(converter = JsonAttributeConverter.class)
  @Column(name = "tags")
  private Object tags;
  @Column(name = "is_bookmarked", nullable = false)
  private Boolean isBookmarked = false;
  @Column(name = "last_run_at")
  private Instant lastRunAt;
  @Column(name = "run_count", nullable = false)
  private Integer runCount = 0;
}
