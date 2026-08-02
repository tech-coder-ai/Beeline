package com.datalens.model.entity;

import com.datalens.core.persistence.BaseEntity;
import com.datalens.core.persistence.JsonAttributeConverter;
import jakarta.persistence.*;
import java.time.Instant;
import lombok.Getter; import lombok.Setter;

@Entity
@Table(name = "prompt_templates")
@Getter @Setter
public class PromptTemplate extends BaseEntity {
  private String name;
  @Column(nullable = false)
  private Integer version = 1;
  private String template;
  @Column(name = "is_active", nullable = false)
  private Boolean isActive = true;
  private String notes;
}
