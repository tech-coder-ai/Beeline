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
  @Column(name = "from_table_id")
  private String fromTableId;
  @Column(name = "from_column")
  private String fromColumn;
  @Column(name = "to_table_id")
  private String toTableId;
  @Column(name = "to_column")
  private String toColumn;
  @Column(name = "relationship_type")
  private String relationshipType;
  private String source;
  @Column(name = "Double")
  private String confidence;
  @Column(name = "is_approved")
  private Boolean isApproved;
}
