package com.datalens.model.repository;

import com.datalens.model.entity.CalculatedField;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CalculatedFieldRepository extends JpaRepository<CalculatedField, String> {
  List<CalculatedField> findByTableIdOrderByCreatedAtDesc(String tableId);

  List<CalculatedField> findByTableIdInAndIsActiveTrue(java.util.Collection<String> tableIds);
}
