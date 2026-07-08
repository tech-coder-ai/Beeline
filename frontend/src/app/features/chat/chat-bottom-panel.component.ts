import { DecimalPipe } from '@angular/common';
import { Component, computed, input, signal } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { BeelineResponse } from '../../core/models';
import { SqlPanelComponent } from '../../shared/sql-panel.component';

type Tab = 'sql' | 'warnings' | 'cost';

/** Bottom expandable panel: SQL, warnings, cost/estimate details. */
@Component({
  selector: 'bl-chat-bottom-panel',
  imports: [DecimalPipe, MatIconModule, SqlPanelComponent],
  templateUrl: './chat-bottom-panel.component.html',
  styleUrl: './chat-bottom-panel.component.scss',
})
export class ChatBottomPanelComponent {
  readonly response = input<BeelineResponse | null>(null);
  readonly expanded = signal(false);
  readonly activeTab = signal<Tab>('sql');

  readonly warningCount = computed(() => this.response()?.warnings.length ?? 0);
  readonly hasSql = computed(() => !!this.response()?.sql);
  readonly hasCost = computed(() => !!this.response()?.cost_estimate);

  toggle(): void {
    this.expanded.update((e) => !e);
  }

  setTab(tab: Tab): void {
    this.activeTab.set(tab);
    this.expanded.set(true);
  }
}
