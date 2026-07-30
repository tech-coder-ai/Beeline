import { Component, computed, effect, input, signal } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { formatSql } from '../core/sql-format';

@Component({
  selector: 'bl-sql-panel',
  imports: [MatIconModule, MatTooltipModule],
  template: `
    <div class="sql-wrap">
      <div class="sql-header">
        <span class="muted label">{{ label() }}</span>
        <div class="sql-actions">
          <button
            class="icon-btn"
            [class.active]="formatted()"
            [matTooltip]="formatted() ? 'Show compact SQL' : 'Format SQL'"
            (click)="toggleFormat()"
          >
            <mat-icon>{{ formatted() ? 'wrap_text' : 'subject' }}</mat-icon>
          </button>
          <button class="icon-btn" matTooltip="Copy SQL" (click)="copy()">
            <mat-icon>{{ copied() ? 'check' : 'content_copy' }}</mat-icon>
          </button>
        </div>
      </div>
      <pre class="sql-block" [class.scrollable]="scrollable()" [class.formatted]="formatted()">{{ displaySql() }}</pre>
    </div>
  `,
  styles: [`
    .sql-wrap { width: 100%; }
    .sql-header {
      display: flex; justify-content: space-between; align-items: center;
      margin-bottom: 4px;
      .label { font-size: 11.5px; text-transform: uppercase; letter-spacing: 0.05em; font-weight: 600; }
    }
    .sql-actions {
      display: flex;
      gap: 2px;
    }
    pre { margin: 0; }
    pre.scrollable {
      max-height: 320px;
      overflow: auto;
    }
    pre.formatted {
      white-space: pre;
    }
    pre:not(.formatted) {
      white-space: pre-wrap;
      word-break: break-word;
    }
  `],
})
export class SqlPanelComponent {
  readonly sql = input.required<string>();
  readonly label = input('Generated SQL');
  readonly scrollable = input(false);
  readonly copied = signal(false);
  readonly formatted = signal(true);

  readonly displaySql = computed(() => {
    const raw = this.sql();
    return this.formatted() ? formatSql(raw) : raw;
  });

  constructor() {
    effect(() => {
      this.sql();
      this.formatted.set(true);
    });
  }

  toggleFormat(): void {
    this.formatted.update((v) => !v);
  }

  copy(): void {
    navigator.clipboard.writeText(this.displaySql());
    this.copied.set(true);
    setTimeout(() => this.copied.set(false), 1500);
  }
}
