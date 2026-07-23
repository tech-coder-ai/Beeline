package com.datalens.model.repository;

import com.datalens.model.entity.PromptTemplate;
import org.springframework.data.jpa.repository.JpaRepository;

public interface PromptTemplateRepository extends JpaRepository<PromptTemplate, String> {}
