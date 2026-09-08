package com.datalens.model.entity;

import com.datalens.core.persistence.BaseEntity;
import jakarta.persistence.Column;
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

  /**
   * When set, this abbreviation refers to a catalog governance classification (e.g. "CDE" ->
   * "critical") rather than a business data value - answered directly from catalog metadata
   * (see PipelineStages.answerGovernanceQuestion) without needing to fuzzy-match {@code value}
   * against whatever classification strings happen to exist.
   */
  @Column(name = "maps_to_classification")
  private String mapsToClassification;
}
