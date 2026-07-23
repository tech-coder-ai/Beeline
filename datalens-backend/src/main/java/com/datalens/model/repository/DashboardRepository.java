package com.datalens.model.repository;

import com.datalens.model.entity.Dashboard;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface DashboardRepository extends JpaRepository<Dashboard, String> {
  List<Dashboard> findAllByOrderByUpdatedAtDesc();
}
