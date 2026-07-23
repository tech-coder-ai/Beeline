package com.datalens.model.repository;

import com.datalens.model.entity.SavedQuery;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface SavedQueryRepository extends JpaRepository<SavedQuery, String> {
  List<SavedQuery> findAllByOrderByUpdatedAtDesc();
}
