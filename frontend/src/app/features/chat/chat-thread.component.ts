import {
  Component,
  ElementRef,
  OnDestroy,
  afterRenderEffect,
  effect,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { ChatStateService } from '../../core/chat-state.service';
import { DataLensResponse, ClarificationOption } from '../../core/models';
import { ResponseRendererComponent } from '../../shared/response-renderer.component';
import { LogoMarkComponent } from '../../shared/logo-mark.component';

const PROCESSING_STAGES = [
  'Understanding your question…',
  'Searching the data catalog…',
  'Planning the query…',
  'Generating SQL…',
  'Validating against Hive…',
  'Executing and summarizing…',
];

@Component({
  selector: 'bl-chat-thread',
  imports: [FormsModule, MatIconModule, MatTooltipModule, ResponseRendererComponent, LogoMarkComponent],
  templateUrl: './chat-thread.component.html',
  styleUrl: './chat-thread.component.scss',
})
export class ChatThreadComponent implements OnDestroy {
  readonly state = inject(ChatStateService);
  readonly scrollEl = viewChild<ElementRef<HTMLDivElement>>('scroll');
  readonly editInputEl = viewChild<ElementRef<HTMLTextAreaElement>>('editInput');
  readonly editingMessageId = signal<string | null>(null);
  readonly processingStage = signal(PROCESSING_STAGES[0]);
  editText = '';
  private stageTimer: ReturnType<typeof setInterval> | null = null;

  constructor() {
    afterRenderEffect(() => {
      this.state.messages();
      this.state.sending();
      this.scrollToBottom();
    });
    effect(() => {
      if (this.state.sending()) {
        this.startStageCycle();
      } else {
        this.stopStageCycle();
      }
    });
  }

  ngOnDestroy(): void {
    this.stopStageCycle();
  }

  private startStageCycle(): void {
    if (this.stageTimer) return;
    let index = 0;
    this.processingStage.set(PROCESSING_STAGES[0]);
    this.stageTimer = setInterval(() => {
      index = Math.min(index + 1, PROCESSING_STAGES.length - 1);
      this.processingStage.set(PROCESSING_STAGES[index]);
    }, 2500);
  }

  private stopStageCycle(): void {
    if (this.stageTimer) {
      clearInterval(this.stageTimer);
      this.stageTimer = null;
    }
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

  onExecutePreview(executionId: string | null | undefined, sql?: string): void {
    if (!executionId) return;
    this.state.send('', { execute_preview_id: executionId, execute_preview_sql: sql?.trim() || undefined });
  }

  onFollowUp(question: string): void {
    this.state.send(question);
  }

  onRefine(messageId: string): void {
    this.state.refineQuestion(messageId);
  }

  onSaveQuery(response: DataLensResponse): void {
    this.state.saveQuery(response);
  }

  onPinToDashboard(response: DataLensResponse): void {
    this.state.pinToDashboard(response);
  }

  onInspect(messageId: string): void {
    this.state.inspectMessage(messageId);
  }

  startEdit(messageId: string, content: string): void {
    this.editingMessageId.set(messageId);
    this.editText = content;
    queueMicrotask(() => {
      const el = this.editInputEl()?.nativeElement;
      if (!el) return;
      el.focus();
      el.setSelectionRange(el.value.length, el.value.length);
      this.autoGrowEdit(el);
    });
  }

  autoGrowEdit(el: HTMLTextAreaElement): void {
    el.style.height = 'auto';
    el.style.height = `${Math.min(Math.max(el.scrollHeight, 120), 280)}px`;
  }

  onEditEnter(event: Event, messageId: string): void {
    const keyboardEvent = event as KeyboardEvent;
    if (!keyboardEvent.shiftKey) {
      keyboardEvent.preventDefault();
      this.submitEdit(messageId);
    }
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
