package com.datalens.model.repository;

import com.datalens.model.entity.GlossaryTerm;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface GlossaryTermRepository extends JpaRepository<GlossaryTerm, String> {
  Optional<GlossaryTerm> findByTermIgnoreCase(String term);
}
