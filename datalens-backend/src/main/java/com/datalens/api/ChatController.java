package com.datalens.api;

import com.datalens.schema.api.*;
import com.datalens.service.ChatService;
import java.util.List;
import java.util.Map;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("${datalens.api-prefix}/chat")
public class ChatController {
  private final ChatService chat;
  public ChatController(ChatService chat) { this.chat = chat; }
  @PostMapping("") public ChatTurnOut send(@RequestBody ChatRequest req) { return chat.handleTurn(req); }
  @GetMapping("/sessions") public List<ChatSessionOut> sessions(@RequestParam(defaultValue="false") boolean includeArchived, @RequestParam(required=false) String search) {
    return chat.listSessions(includeArchived, search);
  }
  @GetMapping("/sessions/{sessionId}/messages") public List<ChatMessageOut> messages(@PathVariable String sessionId) { return chat.listMessages(sessionId); }
  @PatchMapping("/sessions/{sessionId}") public ChatSessionOut patch(@PathVariable String sessionId, @RequestBody SessionUpdate update) {
    java.util.Map<String, Object> changes = new java.util.HashMap<>();
    if (update.title() != null) changes.put("title", update.title());
    if (update.isPinned() != null) changes.put("is_pinned", update.isPinned());
    if (update.isArchived() != null) changes.put("is_archived", update.isArchived());
    if (update.isShared() != null) changes.put("is_shared", update.isShared());
    var s = chat.updateSession(sessionId, changes);
    return new ChatSessionOut(s.getId(), s.getTitle(), Boolean.TRUE.equals(s.getIsPinned()), Boolean.TRUE.equals(s.getIsArchived()),
        Boolean.TRUE.equals(s.getIsShared()), s.getShareToken(), s.getCreatedAt(), s.getUpdatedAt(), 0);
  }
  @DeleteMapping("/sessions/{sessionId}") public Map<String,String> delete(@PathVariable String sessionId) {
    chat.deleteSession(sessionId); return Map.of("deleted", sessionId);
  }
}
