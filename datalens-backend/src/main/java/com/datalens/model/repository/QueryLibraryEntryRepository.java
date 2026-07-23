package com.datalens.model.repository;

import com.datalens.model.entity.QueryLibraryEntry;
import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface QueryLibraryEntryRepository extends JpaRepository<QueryLibraryEntry, String> {
  List<QueryLibraryEntry> findByIsActiveTrue();

  Optional<QueryLibraryEntry> findByNormalizedQuestionAndConnectorId(String normalizedQuestion, String connectorId);
}
