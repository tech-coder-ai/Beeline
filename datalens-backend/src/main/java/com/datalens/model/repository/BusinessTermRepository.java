package com.datalens.model.repository;

import com.datalens.model.entity.BusinessTerm;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface BusinessTermRepository extends JpaRepository<BusinessTerm, String> {
  List<BusinessTerm> findByStatusOrderByTermAsc(String status);
}
