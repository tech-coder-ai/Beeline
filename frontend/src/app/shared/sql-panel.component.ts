import { Component, input, signal } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';

@Component({
  selector: 'bl-sql-panel',
  imports: [MatIconModule, MatTooltipModule],
  template: `
    <div class="sql-wrap">
      <div class="sql-header">
        <span class="muted label">{{ label() }}</span>
        <button class="icon-btn" matTooltip="Copy SQL" (click)="copy()">
          <mat-icon>{{ copied() ? 'check' : 'content_copy' }}</mat-icon>
        </button>
      </div>
      <pre class="sql-block" [class.scrollable]="scrollable()">{{ sql() }}</pre>
    </div>
  `,
  styles: [`
    .sql-wrap { width: 100%; }
    .sql-header {
      display: flex; justify-content: space-between; align-items: center;
      margin-bottom: 4px;
      .label { font-size: 11.5px; text-transform: uppercase; letter-spacing: 0.05em; font-weight: 600; }
    }
    pre { margin: 0; }
    pre.scrollable {
      max-height: 220px;
      overflow: auto;
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

  copy(): void {
    navigator.clipboard.writeText(this.sql());
    this.copied.set(true);
    setTimeout(() => this.copied.set(false), 1500);
  }
}
