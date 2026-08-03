package com.datalens.model.repository;

import com.datalens.model.entity.CatalogRelationship;
import java.util.Collection;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface CatalogRelationshipRepository extends JpaRepository<CatalogRelationship, String> {
  List<CatalogRelationship> findByFromTableIdOrToTableIdOrderByCreatedAtDesc(
      String fromTableId, String toTableId);

  @Query(
      """
      SELECT r FROM CatalogRelationship r
      WHERE r.isApproved = true
        AND r.fromTableId IN :tableIds
        AND r.toTableId IN :tableIds
      """)
  List<CatalogRelationship> findApprovedAmongTables(@Param("tableIds") Collection<String> tableIds);
}
