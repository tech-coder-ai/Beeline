import { DecimalPipe } from '@angular/common';
import { Component, computed, inject, input, signal } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { FeatureFlagService } from '../../core/feature-flags.service';
import { DataLensResponse } from '../../core/models';
import { SqlPanelComponent } from '../../shared/sql-panel.component';

type Tab = 'sql' | 'warnings' | 'cost' | 'prompts';

/** Bottom expandable panel: SQL, warnings, cost/estimate details, and debug prompts. */
@Component({
  selector: 'bl-chat-bottom-panel',
  imports: [DecimalPipe, MatIconModule, SqlPanelComponent],
  templateUrl: './chat-bottom-panel.component.html',
  styleUrl: './chat-bottom-panel.component.scss',
})
export class ChatBottomPanelComponent {
  private readonly flags = inject(FeatureFlagService);

  readonly response = input<DataLensResponse | null>(null);
  readonly expanded = signal(false);
  readonly activeTab = signal<Tab>('sql');
  readonly expandedPrompt = signal<string | null>(null);

  readonly warningCount = computed(() => this.response()?.warnings.length ?? 0);
  readonly hasSql = computed(() => !!this.response()?.sql);
  readonly hasCost = computed(() => !!this.response()?.cost_estimate);
  readonly showPromptsTab = computed(() => this.flags.debugMode());
  readonly promptCount = computed(() => this.response()?.prompts_used?.length ?? 0);
  readonly hasPrompts = computed(() => this.promptCount() > 0);

  toggle(): void {
    this.expanded.update((e) => !e);
  }

  setTab(tab: Tab): void {
    this.activeTab.set(tab);
    this.expanded.set(true);
  }

  togglePrompt(key: string): void {
    this.expandedPrompt.update((current) => (current === key ? null : key));
  }

  promptKey(index: number, purpose: string): string {
    return `${index}-${purpose}`;
  }
}
