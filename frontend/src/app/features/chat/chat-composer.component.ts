import { Component, ElementRef, effect, inject, output, viewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { ChatStateService } from '../../core/chat-state.service';
import { ConnectorService } from '../../core/connector.service';

const SUGGESTIONS = [
  'Show sales by region for last 6 months',
  'Which products have declining revenue?',
  'Top 20 customers with highest growth',
  'What caused margin reduction in Q2?',
];

@Component({
  selector: 'bl-chat-composer',
  imports: [FormsModule, MatIconModule, MatTooltipModule],
  template: `
    @if (state.messages().length === 0) {
      <div class="suggestions">
        @for (s of suggestions; track s) {
          <button class="suggestion-chip" (click)="sendText(s)">{{ s }}</button>
        }
      </div>
    }
    <div class="composer-meta">
      @if (connectors.connectors().length > 1) {
        <label class="connector-picker">
          <mat-icon>cable</mat-icon>
          <select
            [ngModel]="connectors.activeId()"
            (ngModelChange)="connectors.setActive($event)"
          >
            @for (c of connectors.connectors(); track c.id) {
              <option [value]="c.id">{{ c.display_name || c.id }}</option>
            }
          </select>
        </label>
      } @else if (connectors.activeConnector(); as active) {
        <span class="connector-label muted">
          <mat-icon>cable</mat-icon>{{ active.display_name || active.id }}
        </span>
      }
      @if (state.actionNotice()) {
        <span class="action-notice">{{ state.actionNotice() }}</span>
      }
    </div>
    <div class="composer glass-card">
      <textarea
        #input
        class="composer-input"
        rows="1"
        placeholder="Ask Beeline about your data..."
        [(ngModel)]="text"
        (keydown.enter)="onEnter($event)"
        (input)="autoGrow(input)"
      ></textarea>
      <button
        class="send-btn"
        [disabled]="!text.trim() || state.sending()"
        (click)="send()"
        matTooltip="Send"
      >
        <mat-icon>{{ state.sending() ? 'hourglass_top' : 'send' }}</mat-icon>
      </button>
    </div>
  `,
  styleUrl: './chat-composer.component.scss',
})
export class ChatComposerComponent {
  readonly state = inject(ChatStateService);
  readonly connectors = inject(ConnectorService);
  readonly suggestions = SUGGESTIONS;
  readonly sent = output<void>();
  readonly inputEl = viewChild<ElementRef<HTMLTextAreaElement>>('input');
  text = '';

  constructor() {
    effect(() => {
      const draft = this.state.composerDraft();
      if (!draft) return;
      this.text = draft;
      this.state.composerDraft.set('');
      queueMicrotask(() => {
        const el = this.inputEl()?.nativeElement;
        if (el) {
          el.focus();
          el.setSelectionRange(el.value.length, el.value.length);
          this.autoGrow(el);
        }
      });
    });
    effect(() => {
      const notice = this.state.actionNotice();
      if (!notice) return;
      const timer = setTimeout(() => this.state.actionNotice.set(null), 4000);
      return () => clearTimeout(timer);
    });
  }

  send(): void {
    const message = this.text.trim();
    if (!message || this.state.sending()) return;
    this.text = '';
    this.state.send(message);
    this.sent.emit();
  }

  sendText(message: string): void {
    this.text = message;
    this.send();
  }

  onEnter(event: Event): void {
    const keyboardEvent = event as KeyboardEvent;
    if (!keyboardEvent.shiftKey) {
      keyboardEvent.preventDefault();
      this.send();
    }
  }

  autoGrow(el: HTMLTextAreaElement): void {
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }
}
