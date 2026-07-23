package com.datalens.model.repository;

import com.datalens.model.entity.AuditLog;
import java.util.List;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface AuditLogRepository extends JpaRepository<AuditLog, String> {
  @Query(
      """
      select a from AuditLog a
      where (:action is null or lower(a.action) like lower(concat('%', :action, '%')))
        and (:severity is null or a.severity = :severity)
      order by a.createdAt desc
      """)
  List<AuditLog> findRecent(Pageable pageable, @Param("action") String action, @Param("severity") String severity);
}
