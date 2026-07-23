package com.datalens.model.repository;

import com.datalens.model.entity.ExecutionHistory;
import java.util.List;
import java.util.Optional;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface ExecutionHistoryRepository extends JpaRepository<ExecutionHistory, String> {
  Optional<ExecutionHistory> findTopBySessionIdAndStatusInOrderByCreatedAtDesc(String sessionId, List<String> statuses);

  @Query(
      """
      select e from ExecutionHistory e
      where (:status is null or e.status = :status)
        and (:search is null or lower(e.prompt) like lower(concat('%', :search, '%'))
             or lower(e.optimizedSql) like lower(concat('%', :search, '%')))
      order by e.createdAt desc
      """)
  List<ExecutionHistory> findRecent(Pageable pageable, @Param("status") String status, @Param("search") String search);

  @Query("select e.status, count(e) from ExecutionHistory e group by e.status")
  List<Object[]> countByStatus();

  @Query("select avg(e.executionTimeMs) from ExecutionHistory e where e.executionTimeMs is not null")
  Double avgExecutionMs();
}
