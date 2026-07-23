package com.datalens.model.repository;

import com.datalens.model.entity.CatalogTable;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CatalogTableRepository extends JpaRepository<CatalogTable, String> {
  java.util.List<CatalogTable> findByDatabaseIdAndIsActiveTrue(String databaseId);

  java.util.List<CatalogTable> findByIsActiveTrueOrderByUsageCountDescNameAsc();

  Optional<CatalogTable> findByDatabaseIdAndName(String databaseId, String name);
}
