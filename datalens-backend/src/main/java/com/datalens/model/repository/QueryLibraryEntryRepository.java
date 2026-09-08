package com.datalens.model.repository;

import com.datalens.model.entity.QueryLibraryEntry;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface QueryLibraryEntryRepository extends JpaRepository<QueryLibraryEntry, String> {
  List<QueryLibraryEntry> findByIsActiveTrue();

  /**
   * Deliberately does not filter by normalized_question in SQL: that column is CLOB on Oracle
   * (long-form questions), and Oracle rejects CLOB in an equality predicate with
   * ORA-00932. Callers compare normalizedQuestion in Java instead - see QueryLibraryService.
   */
  List<QueryLibraryEntry> findByConnectorId(String connectorId);
}
