import { Component, computed, inject, OnInit } from '@angular/core';
import { ChatStateService } from '../../core/chat-state.service';
import { ChatBottomPanelComponent } from './chat-bottom-panel.component';
import { ChatComposerComponent } from './chat-composer.component';
import { ChatContextPanelComponent } from './chat-context-panel.component';
import { ChatSidebarComponent } from './chat-sidebar.component';
import { ChatThreadComponent } from './chat-thread.component';

@Component({
  selector: 'bl-chat-page',
  imports: [
    ChatSidebarComponent, ChatThreadComponent, ChatComposerComponent,
    ChatContextPanelComponent, ChatBottomPanelComponent,
  ],
  templateUrl: './chat-page.component.html',
  styleUrl: './chat-page.component.scss',
})
export class ChatPageComponent implements OnInit {
  readonly state = inject(ChatStateService);

  readonly latestResponse = computed(() => this.state.focusedResponse());

  ngOnInit(): void {
    this.state.loadSessions();
  }
}
