package com.datalens.model.entity;

import com.datalens.core.persistence.BaseEntity;
import com.datalens.core.persistence.JsonAttributeConverter;
import jakarta.persistence.*;
import java.time.Instant;
import lombok.Getter; import lombok.Setter;

@Entity
@Table(name = "glossary_terms")
@Getter @Setter
public class GlossaryTerm extends BaseEntity {
  private String term;
  private String definition;
  @Column(name = "business_meaning")
  private String businessMeaning;
  @Convert(converter = JsonAttributeConverter.class)
  @Column(name = "examples")
  private Object examples;
  private String owner;
  @Convert(converter = JsonAttributeConverter.class)
  @Column(name = "tags")
  private Object tags;
  private String status;
  private String source;
}
