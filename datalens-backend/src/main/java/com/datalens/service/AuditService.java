package com.datalens.service;

import com.datalens.model.entity.AuditLog;
import com.datalens.model.repository.AuditLogRepository;
import java.util.Map;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AuditService {
  private final AuditLogRepository repo;

  public AuditService(AuditLogRepository repo) {
    this.repo = repo;
  }

  @Transactional
  public void audit(
      String userId,
      String action,
      String entityType,
      String entityId,
      Map<String, Object> detail,
      String severity) {
    AuditLog log = new AuditLog();
    log.setUserId(userId);
    log.setAction(action);
    log.setEntityType(entityType);
    log.setEntityId(entityId);
    log.setDetail(detail);
    log.setSeverity(severity != null ? severity : "info");
    repo.save(log);
  }
}
