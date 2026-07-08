import { Component, input } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { KpiCard } from '../core/models';

@Component({
  selector: 'bl-kpi-cards',
  imports: [MatIconModule],
  template: `
    <div class="kpi-row">
      @for (card of cards(); track card.label) {
        <div class="kpi glass-card" [class]="card.severity">
          <div class="kpi-label">{{ card.label }}</div>
          <div class="kpi-value">{{ card.value }}<span class="unit">{{ card.unit ?? '' }}</span></div>
          @if (card.trend !== null && card.trend !== undefined) {
            <div class="kpi-trend" [class.up]="card.trend >= 0" [class.down]="card.trend < 0">
              <mat-icon>{{ card.trend >= 0 ? 'trending_up' : 'trending_down' }}</mat-icon>
              {{ card.trend >= 0 ? '+' : '' }}{{ card.trend }}%
              @if (card.trend_label) { <span class="muted">{{ card.trend_label }}</span> }
            </div>
          }
        </div>
      }
    </div>
  `,
  styles: [`
    .kpi-row {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      gap: 12px;
    }
    .kpi {
      padding: 14px 18px;
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    .kpi-label {
      font-size: 12px; font-weight: 500;
      color: var(--bl-text-muted);
      text-transform: uppercase; letter-spacing: 0.04em;
    }
    .kpi-value {
      font-size: 26px; font-weight: 700; line-height: 1.1;
      .unit { font-size: 14px; font-weight: 500; margin-left: 3px; color: var(--bl-text-muted); }
    }
    .kpi-trend {
      display: flex; align-items: center; gap: 4px;
      font-size: 12.5px; font-weight: 600;
      mat-icon { font-size: 16px; width: 16px; height: 16px; }
      &.up { color: var(--bl-good); }
      &.down { color: var(--bl-bad); }
    }
    .kpi.good { border-left: 3px solid var(--bl-good); }
    .kpi.warning { border-left: 3px solid var(--bl-warn); }
    .kpi.bad { border-left: 3px solid var(--bl-bad); }
  `],
})
export class KpiCardsComponent {
  readonly cards = input.required<KpiCard[]>();
}
