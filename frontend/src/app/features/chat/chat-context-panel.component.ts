import { Component, computed, input } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { BeelineResponse } from '../../core/models';

/** Right sidebar: tables used, metadata, suggestions, execution stats. */
@Component({
  selector: 'bl-chat-context-panel',
  imports: [MatIconModule],
  templateUrl: './chat-context-panel.component.html',
  styleUrl: './chat-context-panel.component.scss',
})
export class ChatContextPanelComponent {
  readonly response = input<BeelineResponse | null>(null);

  readonly hasContent = computed(() => {
    const r = this.response();
    return !!r && (r.tables_used.length > 0 || r.filters_used.length > 0 || r.metrics_used.length > 0 || !!r.stats);
  });
}
