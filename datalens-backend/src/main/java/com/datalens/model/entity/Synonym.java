package com.datalens.model.entity;

import com.datalens.core.persistence.BaseEntity;
import com.datalens.core.persistence.JsonAttributeConverter;
import jakarta.persistence.*;
import java.time.Instant;
import lombok.Getter; import lombok.Setter;

@Entity
@Table(name = "synonyms")
@Getter @Setter
public class Synonym extends BaseEntity {
  @Column(name = "term_id")
  private String termId;
  private String synonym;
  private String source;
  @Column(name = "Double")
  private String confidence;
}
