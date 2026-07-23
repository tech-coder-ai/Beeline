package com.datalens.model.repository;

import com.datalens.model.entity.CatalogColumn;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CatalogColumnRepository extends JpaRepository<CatalogColumn, String> {
  void deleteByTableId(String tableId);

  List<CatalogColumn> findByTableIdOrderByPositionAsc(String tableId);
}
