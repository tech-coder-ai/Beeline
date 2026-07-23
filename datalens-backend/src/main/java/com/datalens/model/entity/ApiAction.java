package com.datalens.model.entity;

import com.datalens.core.persistence.BaseEntity;
import com.datalens.core.persistence.JsonAttributeConverter;
import jakarta.persistence.*;
import java.time.Instant;
import lombok.Getter; import lombok.Setter;

@Entity
@Table(name = "api_actions")
@Getter @Setter
public class ApiAction extends BaseEntity {
  @Column(name = "action_id")
  private String actionId;
  private String label;
  private String icon;
  private String method;
  private String url;
  @Convert(converter = JsonAttributeConverter.class)
  @Column(name = "headers")
  private Object headers;
  @Column(name = "body_template")
  private String bodyTemplate;
  private Boolean confirm;
  private Boolean enabled;
}
