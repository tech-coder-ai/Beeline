package com.datalens.model.repository;

import com.datalens.model.entity.Abbreviation;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface AbbreviationRepository extends JpaRepository<Abbreviation, String> {
  List<Abbreviation> findByStatusOrderByAbbreviationAsc(String status);
}
