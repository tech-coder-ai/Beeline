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
  private Integer version;
  private String template;
  @Column(name = "is_active")
  private Boolean isActive;
  private String notes;
}
