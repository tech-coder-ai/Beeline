import { Component, ElementRef, afterRenderEffect, inject, output, viewChild } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { ChatStateService } from '../../core/chat-state.service';
import { ClarificationOption } from '../../core/models';
import { ResponseRendererComponent } from '../../shared/response-renderer.component';

@Component({
  selector: 'bl-chat-thread',
  imports: [MatIconModule, ResponseRendererComponent],
  templateUrl: './chat-thread.component.html',
  styleUrl: './chat-thread.component.scss',
})
export class ChatThreadComponent {
  readonly state = inject(ChatStateService);
  readonly scrollEl = viewChild<ElementRef<HTMLDivElement>>('scroll');
  readonly inspect = output<string>();

  constructor() {
    afterRenderEffect(() => {
      this.state.messages();
      const el = this.scrollEl()?.nativeElement;
      if (el) el.scrollTop = el.scrollHeight;
    });
  }

  onClarify(messageId: string, choice: ClarificationOption | string): void {
    const value = typeof choice === 'string' ? choice : choice.value;
    this.state.send('', { clarification_answer: value });
  }

  onExecutePreview(executionId: string | null | undefined): void {
    if (!executionId) return;
    this.state.send('', { execute_preview_id: executionId });
  }

  onFollowUp(question: string): void {
    this.state.send(question);
  }
}
