package com.datalens.model.entity;

import com.datalens.core.persistence.BaseEntity;
import com.datalens.core.persistence.JsonAttributeConverter;
import jakarta.persistence.*;
import java.time.Instant;
import lombok.Getter; import lombok.Setter;

@Entity
@Table(name = "config_overrides")
@Getter @Setter
public class ConfigOverride extends BaseEntity {
  private String key;
  @Convert(converter = JsonAttributeConverter.class)
  @Column(name = "value")
  private Object value;
  @Column(name = "updated_by")
  private String updatedBy;
}
