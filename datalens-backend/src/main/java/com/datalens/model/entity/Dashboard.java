package com.datalens.model.entity;

import com.datalens.core.persistence.BaseEntity;
import com.datalens.core.persistence.JsonAttributeConverter;
import jakarta.persistence.*;
import java.time.Instant;
import lombok.Getter; import lombok.Setter;

@Entity
@Table(name = "dashboards")
@Getter @Setter
public class Dashboard extends BaseEntity {
  @Column(name = "user_id")
  private String userId;
  private String name;
  private String description;
  @Column(name = "is_shared")
  private Boolean isShared;
  @Column(name = "share_token")
  private String shareToken;
  @Column(name = "refresh_interval_seconds")
  private Integer refreshIntervalSeconds;
  @Convert(converter = JsonAttributeConverter.class)
  @Column(name = "layout")
  private Object layout;
}
