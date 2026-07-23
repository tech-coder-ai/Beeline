package com.datalens.service;

import com.datalens.model.entity.ExecutionHistory;
import com.datalens.model.entity.QueryLibraryEntry;
import com.datalens.model.repository.ExecutionHistoryRepository;
import com.datalens.model.repository.QueryLibraryEntryRepository;
import com.datalens.pipeline.PipelineContext;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class QueryLibraryService {
  private final QueryLibraryEntryRepository library;
  private final ExecutionHistoryRepository history;
  private final ObjectMapper mapper;

  public QueryLibraryService(
      QueryLibraryEntryRepository library, ExecutionHistoryRepository history, ObjectMapper mapper) {
    this.library = library;
    this.history = history;
    this.mapper = mapper;
  }

  public static String normalizeQuestion(String text) {
    return text.toLowerCase().trim().replaceAll("\\s+", " ");
  }

  @Transactional
  public void recordSuccess(PipelineContext ctx) {
    String sql = ctx.getOptimizedSql() != null ? ctx.getOptimizedSql() : ctx.getSql();
    if (sql == null || sql.isBlank()) return;
    String normalized = normalizeQuestion(ctx.effectivePrompt());
    if (ctx.getLibraryMatch() != null) {
      library
          .findById(ctx.getLibraryMatch().getEntryId())
          .ifPresent(
              entry -> {
                entry.setSuccessCount(entry.getSuccessCount() + 1);
                if (ctx.getExecutionTimeMs() > 0) {
                  double prev = entry.getAvgExecutionMs() != null ? entry.getAvgExecutionMs() : ctx.getExecutionTimeMs();
                  entry.setAvgExecutionMs(Math.round(0.7 * prev + 0.3 * ctx.getExecutionTimeMs() * 10) / 10.0);
                }
              });
      return;
    }
    var existing = library.findByNormalizedQuestionAndConnectorId(normalized, ctx.getConnectorId());
    if (existing.isPresent()) {
      QueryLibraryEntry e = existing.get();
      e.setSql(sql);
      e.setSuccessCount(e.getSuccessCount() + 1);
      e.setIsActive(true);
      return;
    }
    QueryLibraryEntry entry = new QueryLibraryEntry();
    entry.setQuestion(ctx.effectivePrompt());
    entry.setNormalizedQuestion(normalized);
    entry.setSql(sql);
    entry.setConnectorId(ctx.getConnectorId());
    if (ctx.getPlan() != null) entry.setTablesUsed(ctx.getPlan().getTables());
    if (ctx.getIntent() != null) entry.setIntent(mapper.convertValue(ctx.getIntent(), java.util.Map.class));
    if (ctx.getPlan() != null) entry.setExecutionPlan(mapper.convertValue(ctx.getPlan(), java.util.Map.class));
    if (ctx.getExecutionTimeMs() > 0) entry.setAvgExecutionMs((double) ctx.getExecutionTimeMs());
    library.save(entry);
  }

  @Transactional
  public void applyFeedback(String executionId, boolean positive) {
    ExecutionHistory h = history.findById(executionId).orElse(null);
    if (h == null || h.getReusedQueryId() == null) return;
    library
        .findById(h.getReusedQueryId())
        .ifPresent(
            entry -> {
              if (positive) entry.setPositiveFeedback(entry.getPositiveFeedback() + 1);
              else {
                entry.setNegativeFeedback(entry.getNegativeFeedback() + 1);
                if (entry.getNegativeFeedback() >= 3 && entry.getNegativeFeedback() > entry.getPositiveFeedback()) {
                  entry.setIsActive(false);
                }
              }
            });
  }
}
