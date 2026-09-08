package com.datalens.model.entity;

import com.datalens.core.persistence.BaseEntity;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;
import lombok.Getter;
import lombok.Setter;

/**
 * A piece of business/functional knowledge that doesn't fit a term definition or a
 * term-to-value binding: conditional logic, governance policy, or a naming/preference
 * convention. The LLM reads {@code statement} as plain text and applies it; nothing in
 * the platform parses or executes rule logic, so this stays domain-agnostic - a
 * deployment's business rules are data, not code.
 */
@Entity
@Table(name = "business_rules")
@Getter
@Setter
public class BusinessRule extends BaseEntity {
  private String name;

  /** global = always included; table/column = retrieved only when that table/column is in play. */
  private String scope;

  /** Qualified table name, e.g. analytics.orders. Null for global-scope rules. */
  private String entity;

  @Column(name = "column_name")
  private String columnName;

  /** Free-text tag such as "filter", "calculation", "governance" - informational only. */
  @Column(name = "rule_type")
  private String ruleType;

  /** The rule itself, in plain language, applied by the LLM as-is. */
  private String statement;

  private String status;
  private String source;
}
