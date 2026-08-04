package com.datalens.model.entity;

import com.datalens.core.persistence.BaseEntity;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;
import lombok.Getter;
import lombok.Setter;

@Entity
@Table(name = "abbreviations")
@Getter
@Setter
public class Abbreviation extends BaseEntity {
  private String abbreviation;
  private String entity;
  private String value;
  private String description;
  private String status;
  private String source;
}
