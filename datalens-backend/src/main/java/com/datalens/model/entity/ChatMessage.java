package com.datalens.model.entity;

import com.datalens.core.persistence.BaseEntity;
import com.datalens.core.persistence.JsonAttributeConverter;
import jakarta.persistence.*;
import java.time.Instant;
import lombok.Getter; import lombok.Setter;

@Entity
@Table(name = "chat_messages")
@Getter @Setter
public class ChatMessage extends BaseEntity {
  @Column(name = "session_id")
  private String sessionId;
  private String role;
  private String content;
  @Convert(converter = JsonAttributeConverter.class)
  @Column(name = "response_payload")
  private Object responsePayload;
  @Column(name = "execution_id")
  private String executionId;
}
