import { isPlatformBrowser, DecimalPipe } from '@angular/common';
import { Component, PLATFORM_ID, computed, inject, input, output } from '@angular/core';
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
          @if (showSaveQuery()) {
            <button class="icon-btn" matTooltip="Save query" (click)="saveQuery.emit()">
              <mat-icon>bookmark_add</mat-icon>
            </button>
          }
          @if (showPinToDashboard()) {
            <button class="icon-btn" matTooltip="Pin to dashboard" (click)="pinToDashboard.emit()">
              <mat-icon>push_pin</mat-icon>
            </button>
          }
          @if (showExplainQuery()) {
            <button class="icon-btn" matTooltip="Explain query" (click)="explainQuery.emit()">
              <mat-icon>psychology_alt</mat-icon>
            </button>
          }
          <button class="icon-btn" matTooltip="Edit question" (click)="regenerate.emit()">
            <mat-icon>edit</mat-icon>
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
        [popupParent]="popupParent"
      />
    </div>
  `,
  styles: [`
    .grid-container {
      display: flex;
      flex-direction: column;
      gap: 6px;
      width: 100%;
      position: relative;
      z-index: 0;
    }
    .grid-toolbar {
      display: flex; align-items: center; gap: 2px;
      .spacer { flex: 1; }
      .rowcount { font-size: 12px; display: flex; gap: 8px; align-items: center; }
    }
    .grid {
      width: 100%;
      border: 1px solid var(--bl-border);
      border-radius: 12px;
      overflow: hidden;
    }
  `],
})
export class DataGridComponent {
  readonly table = input.required<TableSpec>();
  readonly showActions = input(true);
  readonly showSaveQuery = input(true);
  readonly showPinToDashboard = input(true);
  readonly showExplainQuery = input(true);

  readonly saveQuery = output<void>();
  readonly pinToDashboard = output<void>();
  readonly explainQuery = output<void>();
  readonly regenerate = output<void>();

  private theme = inject(ThemeService);
  private platformId = inject(PLATFORM_ID);
  readonly popupParent = isPlatformBrowser(this.platformId) ? document.body : undefined;

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
            backgroundColor: '#171e30',
            foregroundColor: '#e7ecf6',
            headerBackgroundColor: '#1f2940',
            headerTextColor: '#c5d0e6',
            borderColor: 'rgba(255,255,255,0.12)',
            rowHoverColor: 'rgba(255,255,255,0.06)',
            oddRowBackgroundColor: '#1a2338',
          }
        : {
            backgroundColor: '#ffffff',
            foregroundColor: '#1a2333',
            headerBackgroundColor: '#f0f3fa',
            headerTextColor: '#3d4a63',
            borderColor: 'rgba(20,30,60,0.12)',
            rowHoverColor: 'rgba(20,30,60,0.04)',
            oddRowBackgroundColor: '#fafbfd',
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
