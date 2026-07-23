package com.datalens.model.entity;

import com.datalens.core.persistence.BaseEntity;
import com.datalens.core.persistence.JsonAttributeConverter;
import jakarta.persistence.*;
import java.time.Instant;
import lombok.Getter; import lombok.Setter;

@Entity
@Table(name = "business_metrics")
@Getter @Setter
public class BusinessMetric extends BaseEntity {
  private String name;
  private String description;
  private String expression;
  @Column(name = "table_qualified_name")
  private String tableQualifiedName;
  private String unit;
  private String aggregation;
  @Column(name = "is_kpi")
  private Boolean isKpi;
  @Convert(converter = JsonAttributeConverter.class)
  @Column(name = "tags")
  private Object tags;
  private String status;
}
