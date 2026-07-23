package com.datalens.model.repository;

import com.datalens.model.entity.SyncRun;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface SyncRunRepository extends JpaRepository<SyncRun, String> {
  List<SyncRun> findTop30ByOrderByCreatedAtDesc();
}
