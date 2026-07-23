package com.datalens.model.repository;

import com.datalens.model.entity.ApprovalItem;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

public interface ApprovalItemRepository extends JpaRepository<ApprovalItem, String> {
  List<ApprovalItem> findByStatusOrderByCreatedAtDesc(String status);

  List<ApprovalItem> findByEntityTypeAndStatusOrderByCreatedAtDesc(String entityType, String status);

  @Query("select a.entityType, count(a) from ApprovalItem a where a.status = 'pending' group by a.entityType")
  List<Object[]> countPendingByEntityType();
}
