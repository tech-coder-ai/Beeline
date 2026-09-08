package com.datalens.model.repository;

import com.datalens.model.entity.BusinessRule;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface BusinessRuleRepository extends JpaRepository<BusinessRule, String> {
  List<BusinessRule> findByStatusOrderByNameAsc(String status);

  List<BusinessRule> findByStatusAndScopeOrderByNameAsc(String status, String scope);
}
