package com.datalens.model.repository;

import com.datalens.model.entity.CatalogDatabase;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CatalogDatabaseRepository extends JpaRepository<CatalogDatabase, String> {
  Optional<CatalogDatabase> findByConnectorIdAndName(String connectorId, String name);
}
