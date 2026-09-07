package com.datalens.model.repository;

import com.datalens.model.entity.CatalogColumn;
import java.util.Collection;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

public interface CatalogColumnRepository extends JpaRepository<CatalogColumn, String> {
  void deleteByTableId(String tableId);

  List<CatalogColumn> findByTableIdOrderByPositionAsc(String tableId);

  List<CatalogColumn> findByTableIdInOrderByTableIdAscPositionAsc(Collection<String> tableIds);

  List<CatalogColumn> findByClassification(String classification);

  @Query(
      "SELECT DISTINCT c.classification FROM CatalogColumn c "
          + "WHERE c.classification IS NOT NULL AND c.classification <> ''")
  List<String> findDistinctClassifications();
}
