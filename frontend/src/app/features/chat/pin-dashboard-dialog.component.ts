import { Component, inject, input, output, signal, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { ApiService } from '../../core/api.service';
import { ConnectorService } from '../../core/connector.service';
import { buildWidgetSnapshot, widgetTitleFor, widgetTypeFor } from '../../core/dashboard-utils';
import { BeelineResponse, Dashboard } from '../../core/models';

@Component({
  selector: 'bl-pin-dashboard-dialog',
  imports: [FormsModule, MatIconModule],
  template: `
    <div class="overlay" (click)="cancel()">
      <div class="dialog glass-card" (click)="$event.stopPropagation()">
        <div class="dialog-header">
          <h3>Pin to dashboard</h3>
          <button class="icon-btn" (click)="cancel()"><mat-icon>close</mat-icon></button>
        </div>

        <p class="muted subtitle">Choose where to save this result.</p>

        @if (loading()) {
          <p class="muted">Loading dashboards...</p>
        } @else {
          <div class="dash-options">
            @for (d of dashboards(); track d.id) {
              <label class="dash-option" [class.selected]="selectedId() === d.id">
                <input
                  type="radio"
                  name="dashboard"
                  [value]="d.id"
                  [checked]="selectedId() === d.id"
                  (change)="selectedId.set(d.id!)"
                />
                <mat-icon>dashboard</mat-icon>
                <span>{{ d.name }}</span>
              </label>
            }
          </div>

          <div class="create-row">
            <label class="create-toggle">
              <input type="checkbox" [(ngModel)]="createNew" (ngModelChange)="onCreateToggle()" />
              Create new dashboard
            </label>
            @if (createNew) {
              <input
                class="text-input"
                placeholder="New dashboard name"
                [(ngModel)]="newDashboardName"
              />
            }
          </div>
        }

        <div class="dialog-actions">
          <button class="ghost-btn" (click)="cancel()">Cancel</button>
          <button
            class="primary-btn"
            [disabled]="pinning() || (!createNew && !selectedId()) || (createNew && !newDashboardName.trim())"
            (click)="confirm()"
          >
            <mat-icon>push_pin</mat-icon>
            {{ pinning() ? 'Pinning...' : 'Pin' }}
          </button>
        </div>
      </div>
    </div>
  `,
  styles: [`
    .overlay {
      position: fixed;
      inset: 0;
      background: rgba(10, 16, 30, 0.45);
      display: flex;
      align-items: center;
      justify-content: center;
      z-index: 1000;
      padding: 24px;
    }
    .dialog {
      width: min(440px, 100%);
      padding: 20px;
      display: flex;
      flex-direction: column;
      gap: 14px;
    }
    .dialog-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      h3 { margin: 0; font-size: 16px; }
    }
    .subtitle { margin: 0; font-size: 13px; }
    .dash-options {
      display: flex;
      flex-direction: column;
      gap: 6px;
      max-height: 220px;
      overflow-y: auto;
    }
    .dash-option {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 10px 12px;
      border-radius: 10px;
      border: 1px solid var(--bl-border);
      cursor: pointer;
      font-size: 13.5px;
      &.selected {
        border-color: var(--bl-accent);
        background: var(--bl-accent-soft);
      }
      input { margin: 0; }
      mat-icon { font-size: 18px; width: 18px; height: 18px; color: var(--bl-accent); }
    }
    .create-row {
      display: flex;
      flex-direction: column;
      gap: 8px;
      padding-top: 4px;
      border-top: 1px solid var(--bl-border);
    }
    .create-toggle {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 13px;
      cursor: pointer;
    }
    .dialog-actions {
      display: flex;
      justify-content: flex-end;
      gap: 10px;
      padding-top: 4px;
    }
  `],
})
export class PinDashboardDialogComponent implements OnInit {
  readonly response = input.required<BeelineResponse>();
  readonly closed = output<void>();
  readonly pinned = output<{ dashboardId: string; dashboardName: string }>();

  private api = inject(ApiService);
  private connectors = inject(ConnectorService);

  readonly dashboards = signal<Dashboard[]>([]);
  readonly selectedId = signal<string | null>(null);
  readonly loading = signal(true);
  readonly pinning = signal(false);
  createNew = false;
  newDashboardName = 'My dashboard';

  ngOnInit(): void {
    this.api.listDashboards().subscribe({
      next: (dashboards) => {
        this.dashboards.set(dashboards);
        if (dashboards.length && dashboards[0].id) {
          this.selectedId.set(dashboards[0].id);
        } else {
          this.createNew = true;
        }
        this.loading.set(false);
      },
      error: () => this.loading.set(false),
    });
  }

  onCreateToggle(): void {
    if (this.createNew) this.selectedId.set(null);
  }

  cancel(): void {
    this.closed.emit();
  }

  confirm(): void {
    const response = this.response();
    if (!response.sql) return;
    this.pinning.set(true);

    const doPin = (dashboardId: string, dashboardName: string) => {
      this.api.addWidget(dashboardId, {
        title: widgetTitleFor(response),
        widget_type: widgetTypeFor(response),
        size: response.table && response.table.rows.length > 20 ? 'full' : 'half',
        sql: response.sql,
        connector_id: this.connectors.activeId(),
        snapshot: buildWidgetSnapshot(response),
        source_execution_id: response.execution_id,
      }).subscribe({
        next: () => {
          this.pinning.set(false);
          this.pinned.emit({ dashboardId, dashboardName });
        },
        error: () => {
          this.pinning.set(false);
          this.closed.emit();
        },
      });
    };

    if (this.createNew) {
      const name = this.newDashboardName.trim();
      if (!name) return;
      this.api.createDashboard({ name, description: 'Pinned from chat' }).subscribe({
        next: (dash) => {
          if (dash.id) doPin(dash.id, dash.name);
          else this.pinning.set(false);
        },
        error: () => this.pinning.set(false),
      });
    } else {
      const id = this.selectedId();
      const dash = this.dashboards().find((d) => d.id === id);
      if (id && dash) doPin(id, dash.name);
      else this.pinning.set(false);
    }
  }
}
