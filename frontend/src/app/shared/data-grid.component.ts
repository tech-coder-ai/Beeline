import { DecimalPipe } from '@angular/common';
import { Component, computed, inject, input, output } from '@angular/core';
import { AgGridAngular } from 'ag-grid-angular';
import {
  AllCommunityModule,
  ColDef,
  ModuleRegistry,
  themeQuartz,
} from 'ag-grid-community';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { TableSpec } from '../core/models';
import { ThemeService } from '../core/theme.service';

ModuleRegistry.registerModules([AllCommunityModule]);

/** AG Grid result table with the full grid action bar (export, copy, save, pin...). */
@Component({
  selector: 'bl-data-grid',
  imports: [AgGridAngular, MatIconModule, MatTooltipModule, DecimalPipe],
  template: `
    <div class="grid-container">
      <div class="grid-toolbar">
        <span class="muted rowcount">
          {{ table().total_rows | number }} rows
          @if (table().truncated) { <span class="chip warn">truncated</span> }
        </span>
        <span class="spacer"></span>
        <button class="icon-btn" matTooltip="Export CSV" (click)="exportCsv()">
          <mat-icon>download</mat-icon>
        </button>
        <button class="icon-btn" matTooltip="Download JSON" (click)="exportJson()">
          <mat-icon>data_object</mat-icon>
        </button>
        <button class="icon-btn" matTooltip="Copy to clipboard" (click)="copy()">
          <mat-icon>content_copy</mat-icon>
        </button>
        @if (showActions()) {
          <button class="icon-btn" matTooltip="Save query" (click)="saveQuery.emit()">
            <mat-icon>bookmark_add</mat-icon>
          </button>
          <button class="icon-btn" matTooltip="Pin to dashboard" (click)="pinToDashboard.emit()">
            <mat-icon>push_pin</mat-icon>
          </button>
          <button class="icon-btn" matTooltip="Explain query" (click)="explainQuery.emit()">
            <mat-icon>psychology_alt</mat-icon>
          </button>
          <button class="icon-btn" matTooltip="Regenerate SQL" (click)="regenerate.emit()">
            <mat-icon>refresh</mat-icon>
          </button>
        }
      </div>
      <ag-grid-angular
        class="grid"
        [theme]="gridTheme()"
        [rowData]="table().rows"
        [columnDefs]="columnDefs()"
        [defaultColDef]="defaultColDef"
        [pagination]="table().rows.length > 50"
        [paginationPageSize]="50"
        [domLayout]="table().rows.length <= 12 ? 'autoHeight' : 'normal'"
        [style.height]="table().rows.length > 12 ? '420px' : null"
      />
    </div>
  `,
  styles: [`
    .grid-container { display: flex; flex-direction: column; gap: 6px; width: 100%; }
    .grid-toolbar {
      display: flex; align-items: center; gap: 2px;
      .spacer { flex: 1; }
      .rowcount { font-size: 12px; display: flex; gap: 8px; align-items: center; }
    }
    .grid { width: 100%; }
  `],
})
export class DataGridComponent {
  readonly table = input.required<TableSpec>();
  readonly showActions = input(true);

  readonly saveQuery = output<void>();
  readonly pinToDashboard = output<void>();
  readonly explainQuery = output<void>();
  readonly regenerate = output<void>();

  private theme = inject(ThemeService);

  readonly defaultColDef: ColDef = {
    sortable: true,
    filter: true,
    resizable: true,
    flex: 1,
    minWidth: 110,
  };

  readonly gridTheme = computed(() =>
    themeQuartz.withParams(
      this.theme.dark()
        ? {
            backgroundColor: 'transparent',
            foregroundColor: '#e7ecf6',
            headerBackgroundColor: 'rgba(255,255,255,0.04)',
            borderColor: 'rgba(255,255,255,0.09)',
            rowHoverColor: 'rgba(255,255,255,0.05)',
          }
        : {
            backgroundColor: 'transparent',
            headerBackgroundColor: 'rgba(20,30,60,0.04)',
            borderColor: 'rgba(20,30,60,0.1)',
          },
    ),
  );

  readonly columnDefs = computed<ColDef[]>(() =>
    this.table().columns.map((col) => ({
      field: col.field,
      headerName: col.header,
      type: col.is_metric ? 'rightAligned' : undefined,
      valueFormatter:
        col.data_type === 'number'
          ? (p) => (typeof p.value === 'number' ? p.value.toLocaleString() : (p.value ?? ''))
          : undefined,
    })),
  );

  exportCsv(): void {
    const table = this.table();
    const header = table.columns.map((c) => c.header).join(',');
    const lines = table.rows.map((row) =>
      table.columns
        .map((c) => {
          const v = row[c.field];
          const s = v === null || v === undefined ? '' : String(v);
          return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
        })
        .join(','),
    );
    this.download([header, ...lines].join('\n'), 'beeline-result.csv', 'text/csv');
  }

  exportJson(): void {
    this.download(JSON.stringify(this.table().rows, null, 2), 'beeline-result.json', 'application/json');
  }

  copy(): void {
    const table = this.table();
    const header = table.columns.map((c) => c.header).join('\t');
    const lines = table.rows.map((r) => table.columns.map((c) => r[c.field] ?? '').join('\t'));
    navigator.clipboard.writeText([header, ...lines].join('\n'));
  }

  private download(content: string, filename: string, type: string): void {
    const blob = new Blob([content], { type });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }
}
