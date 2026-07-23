package com.datalens.model.repository;

import com.datalens.model.entity.Feedback;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface FeedbackRepository extends JpaRepository<Feedback, String> {
  @Query(
      """
      select f from Feedback f
      where (:status is null or f.status = :status)
      order by f.createdAt desc
      """)
  List<Feedback> findRecent(@Param("status") String status);
}
