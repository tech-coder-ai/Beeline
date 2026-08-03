package com.datalens.model.entity;

import com.datalens.core.persistence.BaseEntity;
import com.datalens.core.persistence.JsonAttributeConverter;
import jakarta.persistence.*;
import java.time.Instant;
import lombok.Getter; import lombok.Setter;

@Entity
@Table(name = "catalog_relationships")
@Getter @Setter
public class CatalogRelationship extends BaseEntity {
  @Column(name = "from_table_id", nullable = false)
  private String fromTableId;
  @Column(name = "from_column", nullable = false)
  private String fromColumn;
  @Column(name = "to_table_id", nullable = false)
  private String toTableId;
  @Column(name = "to_column", nullable = false)
  private String toColumn;
  @Convert(converter = JsonAttributeConverter.class)
  @Column(name = "from_columns")
  private Object fromColumns;
  @Convert(converter = JsonAttributeConverter.class)
  @Column(name = "to_columns")
  private Object toColumns;
  @Column(name = "relationship_type", nullable = false)
  private String relationshipType = "many_to_one";
  @Column(name = "join_type", nullable = false)
  private String joinType = "inner";
  private String description;
  @Column(nullable = false)
  private String source = "manual";
  private Double confidence;
  @Column(name = "is_approved", nullable = false)
  private Boolean isApproved = true;
}
