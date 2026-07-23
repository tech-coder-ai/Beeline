package com.datalens.model.repository;

import com.datalens.model.entity.Synonym;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface SynonymRepository extends JpaRepository<Synonym, String> {
  List<Synonym> findByTermId(String termId);

  void deleteByTermId(String termId);
}
