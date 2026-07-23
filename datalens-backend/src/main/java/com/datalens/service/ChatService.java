package com.datalens.service;

import com.datalens.core.exception.NotFound;
import com.datalens.core.exception.ValidationFailed;
import com.datalens.core.json.JsonSafe;
import com.datalens.model.entity.ChatMessage;
import com.datalens.model.entity.ChatSession;
import com.datalens.model.entity.ExecutionHistory;
import com.datalens.model.repository.ChatMessageRepository;
import com.datalens.model.repository.ChatSessionRepository;
import com.datalens.model.repository.ExecutionHistoryRepository;
import com.datalens.pipeline.ExecutionPlanModel;
import com.datalens.pipeline.IntentModel;
import com.datalens.pipeline.Orchestrator;
import com.datalens.pipeline.PipelineContext;
import com.datalens.schema.api.ChatMessageOut;
import com.datalens.schema.api.ChatRequest;
import com.datalens.schema.api.ChatSessionOut;
import com.datalens.schema.api.ChatTurnOut;
import com.datalens.schema.response.DataLensResponseDto;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.security.SecureRandom;
import java.time.Instant;
import java.util.Base64;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ChatService {
  private final ChatSessionRepository sessions;
  private final ChatMessageRepository messages;
  private final ExecutionHistoryRepository history;
  private final Orchestrator orchestrator;
  private final JsonSafe jsonSafe;
  private final ObjectMapper mapper;
  private final com.datalens.config.DataLensSettings settings;

  public ChatService(
      ChatSessionRepository sessions,
      ChatMessageRepository messages,
      ExecutionHistoryRepository history,
      Orchestrator orchestrator,
      JsonSafe jsonSafe,
      ObjectMapper mapper,
      com.datalens.config.DataLensSettings settings) {
    this.sessions = sessions;
    this.messages = messages;
    this.history = history;
    this.orchestrator = orchestrator;
    this.jsonSafe = jsonSafe;
    this.mapper = mapper;
    this.settings = settings;
  }

  public List<ChatSessionOut> listSessions(boolean includeArchived, String search) {
    return sessions.findByUserIdOrderByIsPinnedDescUpdatedAtDesc("default").stream()
        .filter(s -> includeArchived || !Boolean.TRUE.equals(s.getIsArchived()))
        .filter(s -> search == null || search.isBlank() || s.getTitle().toLowerCase().contains(search.toLowerCase()))
        .map(s -> new ChatSessionOut(
            s.getId(), s.getTitle(), Boolean.TRUE.equals(s.getIsPinned()), Boolean.TRUE.equals(s.getIsArchived()),
            Boolean.TRUE.equals(s.getIsShared()), s.getShareToken(), s.getCreatedAt(), s.getUpdatedAt(),
            (int) messages.countBySessionId(s.getId())))
        .toList();
  }

  public List<ChatMessageOut> listMessages(String sessionId) {
    getSession(sessionId);
    return messages.findBySessionIdOrderByCreatedAtAsc(sessionId).stream()
        .map(m -> new ChatMessageOut(
            m.getId(), m.getRole(), m.getContent(),
            m.getResponsePayload() instanceof Map<?, ?> mp ? (Map<String, Object>) mp : null,
            m.getExecutionId(), m.getCreatedAt()))
        .toList();
  }

  @Transactional
  public ChatSession updateSession(String sessionId, Map<String, Object> updates) {
    ChatSession session = getSession(sessionId);
    if (updates.containsKey("title") && updates.get("title") != null) session.setTitle(String.valueOf(updates.get("title")));
    if (updates.containsKey("is_pinned") && updates.get("is_pinned") != null) {
      session.setIsPinned(Boolean.parseBoolean(String.valueOf(updates.get("is_pinned"))));
    }
    if (updates.containsKey("is_archived") && updates.get("is_archived") != null) {
      session.setIsArchived(Boolean.parseBoolean(String.valueOf(updates.get("is_archived"))));
    }
    if (updates.containsKey("is_shared") && updates.get("is_shared") != null) {
      session.setIsShared(Boolean.parseBoolean(String.valueOf(updates.get("is_shared"))));
      if (Boolean.TRUE.equals(session.getIsShared()) && session.getShareToken() == null) session.setShareToken(token());
    }
    return sessions.save(session);
  }

  @Transactional
  public void deleteSession(String sessionId) {
    sessions.delete(getSession(sessionId));
  }

  @Transactional
  public ChatTurnOut handleTurn(ChatRequest request) {
    if (request.executePreviewId() != null && !request.executePreviewId().isBlank()) {
      return executePreview(request.executePreviewId());
    }
    String effective = request.message() != null ? request.message().strip() : "";
    if (effective.isBlank() && request.clarificationAnswer() != null) effective = request.clarificationAnswer().strip();
    if (effective.isBlank()) throw new ValidationFailed("Message must not be empty");
    ChatSession session = ensureSession(request, effective);
    PipelineContext ctx = buildContext(session, request, effective);
    ChatMessage user = new ChatMessage();
    user.setSessionId(session.getId());
    user.setRole("user");
    user.setContent(effective);
    messages.save(user);
    DataLensResponseDto response = orchestrator.run(ctx);
    ChatMessage assistant = new ChatMessage();
    assistant.setSessionId(session.getId());
    assistant.setRole("assistant");
    assistant.setContent(response.getSummary());
    assistant.setResponsePayload(jsonSafe.toMap(response));
    assistant.setExecutionId(response.getExecutionId());
    messages.save(assistant);
    session.setUpdatedAt(Instant.now());
    sessions.save(session);
    return new ChatTurnOut(session.getId(), assistant.getId(), response);
  }

  private ChatTurnOut executePreview(String executionId) {
    ExecutionHistory h = history.findById(executionId).orElseThrow(() -> new NotFound("No pending preview found for this id"));
    if (!"preview".equals(h.getStatus())) throw new NotFound("No pending preview found for this id");
    PipelineContext ctx = new PipelineContext();
    ctx.setPrompt(h.getPrompt());
    ctx.setSessionId(h.getSessionId());
    ctx.setUserId(h.getUserId());
    ctx.setConnectorId(h.getConnectorId());
    ctx.setExecutionId(h.getId());
    ctx.setSql(h.getGeneratedSql());
    ctx.setOptimizedSql(h.getOptimizedSql());
    if (h.getCostEstimate() instanceof Map<?, ?> m) ctx.setCost((Map<String, Object>) m);
    if (h.getConfidence() instanceof Map<?, ?> m) {
      m.forEach((k, v) -> ctx.getConfidence().put(String.valueOf(k), ((Number) v).doubleValue()));
    }
    if (h.getExecutionPlan() != null) ctx.setPlan(mapper.convertValue(h.getExecutionPlan(), ExecutionPlanModel.class));
    if (h.getIntent() != null) ctx.setIntent(mapper.convertValue(h.getIntent(), IntentModel.class));
    DataLensResponseDto response;
    try {
      response = orchestrator.executeAndRespond(ctx, h);
    } catch (Exception e) {
      throw new RuntimeException(e);
    }
    response.setExecutionId(h.getId());
    history.save(h);
    ChatMessage assistant = new ChatMessage();
    assistant.setSessionId(h.getSessionId());
    assistant.setRole("assistant");
    assistant.setContent(response.getSummary());
    assistant.setResponsePayload(jsonSafe.toMap(response));
    assistant.setExecutionId(h.getId());
    messages.save(assistant);
    return new ChatTurnOut(h.getSessionId() != null ? h.getSessionId() : "", assistant.getId(), response);
  }

  private ChatSession ensureSession(ChatRequest request, String effective) {
    if (request.sessionId() != null && !request.sessionId().isBlank()) return getSession(request.sessionId());
    ChatSession session = new ChatSession();
    session.setTitle(effective.length() > 60 ? effective.substring(0, 60) : effective);
    session.setUserId("default");
    session.setConnectorId(request.connectorId());
    return sessions.save(session);
  }

  private PipelineContext buildContext(ChatSession session, ChatRequest request, String effective) {
    int maxHistory = ((Number) settings.get("pipeline.context.max_history_messages", 12)).intValue();
    List<ChatMessage> prior = messages.findBySessionIdOrderByCreatedAtAsc(session.getId());
    PipelineContext ctx = new PipelineContext();
    ctx.setPrompt(effective);
    ctx.setSessionId(session.getId());
    ctx.setUserId("default");
    ctx.setConnectorId(request.connectorId() != null ? request.connectorId() : session.getConnectorId());
    ctx.setClarificationAnswer(request.clarificationAnswer());
    prior.stream().skip(Math.max(0, prior.size() - maxHistory)).forEach(m -> {
      if (m.getContent() != null) ctx.getHistory().add(Map.of("role", m.getRole(), "content", m.getContent()));
    });
    history.findTopBySessionIdAndStatusInOrderByCreatedAtDesc(session.getId(), List.of("executed", "preview"))
        .ifPresent(last -> {
          if (last.getExecutionPlan() != null) ctx.setPreviousPlan(mapper.convertValue(last.getExecutionPlan(), ExecutionPlanModel.class));
          ctx.setPreviousSql(last.getOptimizedSql());
        });
    return ctx;
  }

  private ChatSession getSession(String id) {
    return sessions.findById(id).orElseThrow(() -> new NotFound("Chat session not found"));
  }

  private static String token() {
    byte[] bytes = new byte[18];
    new SecureRandom().nextBytes(bytes);
    return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
  }
}
