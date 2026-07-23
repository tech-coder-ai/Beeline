package com.datalens.model.entity;

import com.datalens.core.persistence.BaseEntity;
import com.datalens.core.persistence.JsonAttributeConverter;
import jakarta.persistence.*;
import java.time.Instant;
import lombok.Getter; import lombok.Setter;

@Entity
@Table(name = "dashboard_widgets")
@Getter @Setter
public class DashboardWidget extends BaseEntity {
  @Column(name = "dashboard_id")
  private String dashboardId;
  private String title;
  @Column(name = "widget_type")
  private String widgetType;
  private Integer position;
  private String size;
  private String sql;
  @Column(name = "connector_id")
  private String connectorId;
  @Convert(converter = JsonAttributeConverter.class)
  @Column(name = "visualization")
  private Object visualization;
  @Convert(converter = JsonAttributeConverter.class)
  @Column(name = "snapshot")
  private Object snapshot;
  @Column(name = "source_execution_id")
  private String sourceExecutionId;
}
