import { Component, ElementRef, afterRenderEffect, inject, signal, viewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { ChatStateService } from '../../core/chat-state.service';
import { BeelineResponse, ClarificationOption } from '../../core/models';
import { ResponseRendererComponent } from '../../shared/response-renderer.component';

@Component({
  selector: 'bl-chat-thread',
  imports: [FormsModule, MatIconModule, MatTooltipModule, ResponseRendererComponent],
  templateUrl: './chat-thread.component.html',
  styleUrl: './chat-thread.component.scss',
})
export class ChatThreadComponent {
  readonly state = inject(ChatStateService);
  readonly scrollEl = viewChild<ElementRef<HTMLDivElement>>('scroll');
  readonly editingMessageId = signal<string | null>(null);
  editText = '';

  constructor() {
    afterRenderEffect(() => {
      this.state.messages();
      this.state.sending();
      this.scrollToBottom();
    });
  }

  private scrollToBottom(): void {
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        const el = this.scrollEl()?.nativeElement;
        if (el) {
          el.scrollTop = el.scrollHeight;
        }
      });
    });
  }

  onClarify(_messageId: string, choice: ClarificationOption | string): void {
    const value = typeof choice === 'string' ? choice : choice.value;
    const label = typeof choice === 'string' ? choice : choice.label;
    this.state.send(label, { clarification_answer: value });
  }

  onExecutePreview(executionId: string | null | undefined): void {
    if (!executionId) return;
    this.state.send('', { execute_preview_id: executionId });
  }

  onFollowUp(question: string): void {
    this.state.send(question);
  }

  onRefine(messageId: string): void {
    this.state.refineQuestion(messageId);
  }

  onSaveQuery(response: BeelineResponse): void {
    this.state.saveQuery(response);
  }

  onPinToDashboard(response: BeelineResponse): void {
    this.state.pinToDashboard(response);
  }

  onInspect(messageId: string): void {
    this.state.inspectMessage(messageId);
  }

  startEdit(messageId: string, content: string): void {
    this.editingMessageId.set(messageId);
    this.editText = content;
  }

  cancelEdit(): void {
    this.editingMessageId.set(null);
    this.editText = '';
  }

  submitEdit(messageId: string): void {
    const text = this.editText.trim();
    if (!text) return;
    this.cancelEdit();
    this.state.editAndResend(messageId, text);
  }

  resendAsIs(messageId: string, content: string): void {
    this.state.editAndResend(messageId, content);
  }
}
