package com.datalens.model.entity;

import com.datalens.core.persistence.BaseEntity;
import com.datalens.core.persistence.JsonAttributeConverter;
import jakarta.persistence.Column;
import jakarta.persistence.Convert;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import lombok.Getter;
import lombok.Setter;

@Entity
@Table(name = "catalog_columns")
@Getter
@Setter
public class CatalogColumn extends BaseEntity {
  @Column(name = "table_id")
  private String tableId;
  private String name;
  private Integer position = 0;
  @Column(name = "data_type")
  private String dataType;
  @Column(name = "inferred_semantic_type")
  private String inferredSemanticType;
  @Column(name = "semantic_confidence")
  private Double semanticConfidence;
  private String description;
  @Column(name = "technical_comment")
  private String technicalComment;
  @Convert(converter = JsonAttributeConverter.class)
  private Object tags;
  private String classification;
  @Column(name = "is_pii")
  private Boolean isPii = false;
  @Column(name = "is_partition")
  private Boolean isPartition = false;
  @Column(name = "is_primary_key")
  private Boolean isPrimaryKey = false;
  @Column(name = "null_percentage")
  private Double nullPercentage;
  @Column(name = "distinct_percentage")
  private Double distinctPercentage;
  @Column(name = "distinct_count")
  private Integer distinctCount;
  @Column(name = "min_value")
  private String minValue;
  @Column(name = "max_value")
  private String maxValue;
  @Convert(converter = JsonAttributeConverter.class)
  @Column(name = "sample_values")
  private Object sampleValues;
  @Convert(converter = JsonAttributeConverter.class)
  @Column(name = "top_values")
  private Object topValues;
  @ManyToOne(fetch = FetchType.LAZY)
  @JoinColumn(name = "table_id", insertable = false, updatable = false)
  private CatalogTable table;
}
