package com.datalens.model.entity;

import com.datalens.core.persistence.BaseEntity;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import lombok.Getter;
import lombok.Setter;

/**
 * User-defined virtual column for a table, e.g. profit_margin = (revenue - cost) / revenue. Not a
 * real column in the source system - expression is inlined into generated SQL wherever the field
 * is referenced.
 */
@Entity
@Table(name = "calculated_fields")
@Getter
@Setter
public class CalculatedField extends BaseEntity {
  @Column(name = "table_id")
  private String tableId;
  private String name;
  private String expression;
  private String description;
  @Column(name = "is_active")
  private Boolean isActive = true;
  private String source = "manual";
  @ManyToOne(fetch = FetchType.LAZY)
  @JoinColumn(name = "table_id", insertable = false, updatable = false)
  private CatalogTable table;
}
