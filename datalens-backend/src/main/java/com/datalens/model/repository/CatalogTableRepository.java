package com.datalens.model.repository;

import com.datalens.model.entity.CatalogTable;
import java.util.Collection;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CatalogTableRepository extends JpaRepository<CatalogTable, String> {
  java.util.List<CatalogTable> findByDatabaseIdAndIsActiveTrue(String databaseId);

  java.util.List<CatalogTable> findByDatabaseIdAndIsActiveTrueAndIsEnabledTrue(String databaseId);

  java.util.List<CatalogTable> findByIsActiveTrueOrderByUsageCountDescNameAsc();

  java.util.List<CatalogTable> findByDatabaseIdInAndIsActiveTrueAndIsEnabledTrueOrderByUsageCountDescNameAsc(
      Collection<String> databaseIds);

  boolean existsByDatabaseIdInAndIsActiveTrueAndIsEnabledTrue(Collection<String> databaseIds);

  Optional<CatalogTable> findByDatabaseIdAndName(String databaseId, String name);
}
