package com.datalens.model.entity;

import com.datalens.core.persistence.BaseEntity;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;
import lombok.Getter;
import lombok.Setter;

@Entity
@Table(name = "business_terms")
@Getter
@Setter
public class BusinessTerm extends BaseEntity {
  private String term;

  /** Qualified table name, e.g. analytics.orders */
  private String entity;

  @Column(name = "column_name")
  private String columnName;

  private String value;

  @Column(name = "table_id")
  private String tableId;

  private String status;
  private String source;
}
