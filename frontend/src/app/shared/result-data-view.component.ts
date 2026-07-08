import { Component, computed, effect, input, output, signal } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { ChartSpec, TableSpec } from '../core/models';
import { ChartComponent } from './chart.component';
import { DataGridComponent } from './data-grid.component';

/** Renders chart and/or table; when both exist, chart is default with a toggle. */
@Component({
  selector: 'bl-result-data-view',
  imports: [MatIconModule, ChartComponent, DataGridComponent],
  template: `
    @if (hasBoth()) {
      <div class="view-toggle">
        <button
          class="ghost-btn small toggle-btn"
          [class.active]="view() === 'chart'"
          (click)="view.set('chart')"
        >
          <mat-icon>show_chart</mat-icon> Chart
        </button>
        <button
          class="ghost-btn small toggle-btn"
          [class.active]="view() === 'table'"
          (click)="view.set('table')"
        >
          <mat-icon>table_rows</mat-icon> Table
        </button>
      </div>
    }

    @if (showChart()) {
      <div class="chart-grid" [class.single]="charts().length === 1">
        @for (chart of charts(); track $index) {
          <div class="glass-card chart-card"><bl-chart [spec]="chart" /></div>
        }
      </div>
    }

    @if (showTable() && table(); as t) {
      <bl-data-grid
        [table]="t"
        [showActions]="showGridActions()"
        [showSaveQuery]="showSaveQuery()"
        [showPinToDashboard]="showPinToDashboard()"
        [showExplainQuery]="showExplainQuery()"
        (saveQuery)="saveQuery.emit()"
        (pinToDashboard)="pinToDashboard.emit()"
        (explainQuery)="explainQuery.emit()"
        (regenerate)="regenerate.emit()"
      />
    }
  `,
  styles: [`
    .view-toggle {
      display: flex;
      gap: 6px;
      margin-bottom: 4px;
    }
    .toggle-btn {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      padding: 6px 12px;
      font-size: 12.5px;
      mat-icon { font-size: 16px; width: 16px; height: 16px; }
      &.active {
        background: var(--bl-accent-soft);
        color: var(--bl-accent);
        border-color: var(--bl-accent);
      }
    }
    .chart-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(380px, 1fr));
      gap: 12px;
      &.single { grid-template-columns: 1fr; }
    }
    .chart-card { padding: 14px 16px; }
  `],
})
export class ResultDataViewComponent {
  readonly table = input<TableSpec | null>(null);
  readonly charts = input<ChartSpec[]>([]);
  readonly showGridActions = input(true);
  readonly showSaveQuery = input(true);
  readonly showPinToDashboard = input(true);
  readonly showExplainQuery = input(true);

  readonly saveQuery = output<void>();
  readonly pinToDashboard = output<void>();
  readonly explainQuery = output<void>();
  readonly regenerate = output<void>();

  readonly view = signal<'chart' | 'table'>('chart');

  readonly hasBoth = computed(
    () => this.charts().length > 0 && (this.table()?.rows?.length ?? 0) > 0,
  );

  readonly showChart = computed(() => {
    if (!this.charts().length) return false;
    return !this.hasBoth() || this.view() === 'chart';
  });

  readonly showTable = computed(() => {
    if (!this.table()?.rows?.length) return false;
    return !this.hasBoth() || this.view() === 'table';
  });

  constructor() {
    effect(() => {
      this.charts();
      this.table();
      this.view.set('chart');
    });
  }
}
