package com.datalens.model.repository;

import com.datalens.model.entity.ChatSession;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ChatSessionRepository extends JpaRepository<ChatSession, String> {
  List<ChatSession> findByUserIdOrderByIsPinnedDescUpdatedAtDesc(String userId);
}
