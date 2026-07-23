package com.datalens.model.repository;

import com.datalens.model.entity.MetadataVersion;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface MetadataVersionRepository extends JpaRepository<MetadataVersion, String> {
  List<MetadataVersion> findByEntityTypeAndEntityIdOrderByCreatedAtDesc(String entityType, String entityId);
}
