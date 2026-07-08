import { Component, computed, inject, OnInit } from '@angular/core';
import { ChatStateService } from '../../core/chat-state.service';
import { ConnectorService } from '../../core/connector.service';
import { ChatBottomPanelComponent } from './chat-bottom-panel.component';
import { ChatComposerComponent } from './chat-composer.component';
import { ChatContextPanelComponent } from './chat-context-panel.component';
import { ChatSidebarComponent } from './chat-sidebar.component';
import { ChatThreadComponent } from './chat-thread.component';
import { PinDashboardDialogComponent } from './pin-dashboard-dialog.component';

@Component({
  selector: 'bl-chat-page',
  imports: [
    ChatSidebarComponent, ChatThreadComponent, ChatComposerComponent,
    ChatContextPanelComponent, ChatBottomPanelComponent, PinDashboardDialogComponent,
  ],
  templateUrl: './chat-page.component.html',
  styleUrl: './chat-page.component.scss',
})
export class ChatPageComponent implements OnInit {
  readonly state = inject(ChatStateService);
  private connectors = inject(ConnectorService);

  readonly latestResponse = computed(() => this.state.focusedResponse());

  ngOnInit(): void {
    this.state.loadSessions();
    this.connectors.load();
  }
}
