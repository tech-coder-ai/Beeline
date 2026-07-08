import { Injectable, computed, inject, signal } from '@angular/core';
import { ApiService } from './api.service';
import { ConnectorService } from './connector.service';
import { BeelineResponse, ChatMessage, ChatSession } from './models';

/** Signal-based chat store: sessions, active thread, pipeline call state. */
@Injectable({ providedIn: 'root' })
export class ChatStateService {
  private api = inject(ApiService);
  private connectors = inject(ConnectorService);

  readonly sessions = signal<ChatSession[]>([]);
  readonly activeSessionId = signal<string | null>(null);
  readonly messages = signal<ChatMessage[]>([]);
  readonly sending = signal(false);
  readonly sessionSearch = signal('');
  readonly error = signal<string | null>(null);
  readonly composerDraft = signal('');
  readonly actionNotice = signal<string | null>(null);
  readonly pinDialogResponse = signal<BeelineResponse | null>(null);

  /** Response currently inspected in the right/bottom panels. */
  readonly focusedResponse = signal<BeelineResponse | null>(null);

  readonly activeSession = computed(
    () => this.sessions().find((s) => s.id === this.activeSessionId()) ?? null,
  );

  loadSessions(): void {
    this.api.listSessions(false, this.sessionSearch()).subscribe({
      next: (sessions) => this.sessions.set(sessions),
      error: () => this.error.set('Failed to load sessions'),
    });
  }

  openSession(sessionId: string | null): void {
    this.activeSessionId.set(sessionId);
    this.focusedResponse.set(null);
    if (!sessionId) {
      this.messages.set([]);
      return;
    }
    this.api.listMessages(sessionId).subscribe({
      next: (messages) => {
        this.messages.set(messages);
        const last = [...messages].reverse().find((m) => m.response_payload);
        this.focusedResponse.set((last?.response_payload as BeelineResponse) ?? null);
      },
      error: () => this.error.set('Failed to load messages'),
    });
  }

  prefillComposer(text: string): void {
    this.composerDraft.set(text);
  }

  inspectMessage(messageId: string): void {
    const message = this.messages().find((m) => m.id === messageId);
    if (message?.response_payload) {
      this.focusedResponse.set(message.response_payload as BeelineResponse);
    }
  }

  refineQuestion(assistantMessageId: string): void {
    const msgs = this.messages();
    const idx = msgs.findIndex((m) => m.id === assistantMessageId);
    if (idx < 0) return;
    for (let i = idx - 1; i >= 0; i--) {
      if (msgs[i].role === 'user' && msgs[i].content) {
        this.prefillComposer(msgs[i].content!);
        return;
      }
    }
    this.actionNotice.set('No prior question found to refine.');
  }

  editAndResend(messageId: string, newText: string): void {
    const trimmed = newText.trim();
    if (!trimmed) return;
    const msgs = this.messages();
    const idx = msgs.findIndex((m) => m.id === messageId);
    if (idx < 0) return;
    this.messages.set(msgs.slice(0, idx));
    this.send(trimmed);
  }

  saveQuery(response: BeelineResponse): void {
    if (!response.sql) {
      this.actionNotice.set('No SQL available to save.');
      return;
    }
    const name = window.prompt('Save query as:', response.metadata?.['refined_prompt'] as string || 'My query');
    if (!name?.trim()) return;
    this.api.saveQuery({
      name: name.trim(),
      sql: response.sql,
      prompt: (response.metadata?.['refined_prompt'] as string) ?? null,
      connector_id: this.connectors.activeId(),
      tags: [],
    }).subscribe({
      next: () => this.actionNotice.set(`Saved query "${name.trim()}"`),
      error: () => this.actionNotice.set('Failed to save query'),
    });
  }

  pinToDashboard(response: BeelineResponse): void {
    if (!response.table?.rows?.length && !response.charts?.length && !response.cards?.length) {
      this.actionNotice.set('No result data to pin — run the query first.');
      return;
    }
    this.pinDialogResponse.set(response);
  }

  closePinDialog(): void {
    this.pinDialogResponse.set(null);
  }

  onPinnedToDashboard(dashboardName: string): void {
    this.pinDialogResponse.set(null);
    this.actionNotice.set(`Pinned to "${dashboardName}"`);
  }

  send(message: string, extras?: { clarification_answer?: string; execute_preview_id?: string }): void {
    if (this.sending()) return;
    this.sending.set(true);
    this.error.set(null);

    if (message) {
      this.messages.update((msgs) => [
        ...msgs,
        {
          id: `local-${Date.now()}`,
          role: 'user',
          content: message,
          created_at: new Date().toISOString(),
        },
      ]);
    }

    this.api
      .sendMessage({
        session_id: this.activeSessionId(),
        message,
        connector_id: this.connectors.activeId(),
        clarification_answer: extras?.clarification_answer ?? null,
        execute_preview_id: extras?.execute_preview_id ?? null,
      })
      .subscribe({
        next: (turn) => {
          this.sending.set(false);
          const isNewSession = !this.activeSessionId();
          this.activeSessionId.set(turn.session_id);
          this.messages.update((msgs) => [
            ...msgs,
            {
              id: turn.message_id,
              role: 'assistant',
              content: turn.response.summary,
              response_payload: turn.response,
              execution_id: turn.response.execution_id,
              created_at: new Date().toISOString(),
            },
          ]);
          this.focusedResponse.set(turn.response);
          if (isNewSession) this.loadSessions();
        },
        error: (err) => {
          this.sending.set(false);
          const detail = err?.error?.message ?? 'Request failed - is the backend running?';
          this.messages.update((msgs) => [
            ...msgs,
            {
              id: `err-${Date.now()}`,
              role: 'assistant',
              content: detail,
              response_payload: {
                kind: 'error',
                summary: detail,
                confidence: { business: 0, metadata: 0, sql: 0, overall: 0 },
                visualization: 'text',
                cards: [], charts: [], insights: [], recommendations: [],
                follow_up_questions: [], tables_used: [], filters_used: [],
                metrics_used: [], warnings: [], actions: [], metadata: {},
                error: detail,
              } as BeelineResponse,
              created_at: new Date().toISOString(),
            },
          ]);
        },
      });
  }

  newChat(): void {
    this.activeSessionId.set(null);
    this.messages.set([]);
    this.focusedResponse.set(null);
  }

  rename(sessionId: string, title: string): void {
    this.api.updateSession(sessionId, { title }).subscribe(() => this.loadSessions());
  }

  togglePin(session: ChatSession): void {
    this.api
      .updateSession(session.id, { is_pinned: !session.is_pinned })
      .subscribe(() => this.loadSessions());
  }

  archive(session: ChatSession): void {
    this.api.updateSession(session.id, { is_archived: true }).subscribe(() => {
      if (this.activeSessionId() === session.id) this.newChat();
      this.loadSessions();
    });
  }

  remove(session: ChatSession): void {
    this.api.deleteSession(session.id).subscribe(() => {
      if (this.activeSessionId() === session.id) this.newChat();
      this.loadSessions();
    });
  }
}
