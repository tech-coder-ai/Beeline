package com.datalens.service;

import com.datalens.model.repository.AuditLogRepository;
import com.datalens.model.repository.ExecutionHistoryRepository;
import com.datalens.model.repository.FeedbackRepository;
import com.datalens.model.repository.SyncRunRepository;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class LogsPurgeService {
  @PersistenceContext private EntityManager em;
  private final ExecutionHistoryRepository executions;
  private final FeedbackRepository feedback;
  private final AuditLogRepository audit;
  private final SyncRunRepository syncRuns;

  public LogsPurgeService(
      ExecutionHistoryRepository executions,
      FeedbackRepository feedback,
      AuditLogRepository audit,
      SyncRunRepository syncRuns) {
    this.executions = executions;
    this.feedback = feedback;
    this.audit = audit;
    this.syncRuns = syncRuns;
  }

  @Transactional
  public java.util.Map<String, Integer> purgeExecutions() {
    int exec = (int) executions.count();
    int fb = (int) feedback.count();
    em.createQuery("update ChatMessage m set m.executionId = null where m.executionId is not null")
        .executeUpdate();
    em.createQuery(
            "update DashboardWidget w set w.sourceExecutionId = null where w.sourceExecutionId is not null")
        .executeUpdate();
    feedback.deleteAll();
    executions.deleteAll();
    return java.util.Map.of("execution_history", exec, "feedback", fb);
  }

  @Transactional
  public java.util.Map<String, Integer> purgeAudit() {
    int n = (int) audit.count();
    audit.deleteAll();
    return java.util.Map.of("audit_logs", n);
  }

  @Transactional
  public java.util.Map<String, Integer> purgeSyncRuns() {
    int n = (int) syncRuns.count();
    syncRuns.deleteAll();
    return java.util.Map.of("sync_runs", n);
  }

  @Transactional
  public java.util.Map<String, Integer> purgeAll(boolean includeSyncRuns) {
    java.util.Map<String, Integer> out = new java.util.LinkedHashMap<>();
    out.putAll(purgeExecutions());
    if (includeSyncRuns) out.putAll(purgeSyncRuns());
    out.putAll(purgeAudit());
    return out;
  }
}
