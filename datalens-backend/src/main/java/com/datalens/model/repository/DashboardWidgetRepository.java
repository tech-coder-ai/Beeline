package com.datalens.model.repository;

import com.datalens.model.entity.DashboardWidget;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface DashboardWidgetRepository extends JpaRepository<DashboardWidget, String> {
  List<DashboardWidget> findByDashboardId(String dashboardId);

  List<DashboardWidget> findByDashboardIdOrderByPositionAsc(String dashboardId);
}
