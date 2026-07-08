import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { MatMenuModule } from '@angular/material/menu';
import { MatTooltipModule } from '@angular/material/tooltip';
import { ChatStateService } from '../../core/chat-state.service';
import { ChatSession } from '../../core/models';

@Component({
  selector: 'bl-chat-sidebar',
  imports: [FormsModule, MatIconModule, MatMenuModule, MatTooltipModule],
  templateUrl: './chat-sidebar.component.html',
  styleUrl: './chat-sidebar.component.scss',
})
export class ChatSidebarComponent {
  readonly state = inject(ChatStateService);
  readonly renamingId = signal<string | null>(null);
  renameValue = '';

  onSearch(value: string): void {
    this.state.sessionSearch.set(value);
    this.state.loadSessions();
  }

  startRename(session: ChatSession, event: Event): void {
    event.stopPropagation();
    this.renamingId.set(session.id);
    this.renameValue = session.title;
  }

  commitRename(session: ChatSession): void {
    if (this.renameValue.trim() && this.renameValue !== session.title) {
      this.state.rename(session.id, this.renameValue.trim());
    }
    this.renamingId.set(null);
  }
}
