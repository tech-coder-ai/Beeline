package com.datalens.model.entity;

import com.datalens.core.persistence.BaseEntity;
import com.datalens.core.persistence.JsonAttributeConverter;
import jakarta.persistence.*;
import java.time.Instant;
import lombok.Getter; import lombok.Setter;

@Entity
@Table(name = "chat_sessions")
@Getter @Setter
public class ChatSession extends BaseEntity {
  private String title;
  @Column(name = "user_id")
  private String userId;
  @Column(name = "is_pinned")
  private Boolean isPinned;
  @Column(name = "is_archived")
  private Boolean isArchived;
  @Column(name = "is_shared")
  private Boolean isShared;
  @Column(name = "share_token")
  private String shareToken;
  @Column(name = "context_summary")
  private String contextSummary;
  @Column(name = "connector_id")
  private String connectorId;
}
