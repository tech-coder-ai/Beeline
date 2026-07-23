package com.datalens.model.repository;

import com.datalens.model.entity.ChatMessage;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ChatMessageRepository extends JpaRepository<ChatMessage, String> {
  List<ChatMessage> findBySessionIdOrderByCreatedAtAsc(String sessionId);
  long countBySessionId(String sessionId);
}
