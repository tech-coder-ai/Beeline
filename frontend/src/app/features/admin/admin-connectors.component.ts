import { DatePipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { ApiService } from '../../core/api.service';
import { ConnectorInfo, ConnectorService } from '../../core/connector.service';
import { SyncRun } from '../../core/models';

@Component({
  selector: 'bl-admin-connectors',
  imports: [DatePipe, FormsModule, MatIconModule],
  templateUrl: './admin-connectors.component.html',
  styleUrl: './admin-connectors.component.scss',
})
export class AdminConnectorsComponent implements OnInit {
  private api = inject(ApiService);
  readonly connectorService = inject(ConnectorService);

  readonly connectors = signal<ConnectorInfo[]>([]);
  readonly defaultId = signal<string>('');
  readonly testResults = signal<Record<string, { ok: boolean; message: string; latency_ms: number }>>({});
  readonly testing = signal<string | null>(null);
  readonly syncRuns = signal<SyncRun[]>([]);
  readonly syncing = signal(false);
  readonly enriching = signal(false);
  readonly saving = signal(false);
  readonly showForm = signal(false);
  readonly editingId = signal<string | null>(null);
  readonly syncConnectorId = signal<string | null>(null);

  form = {
    id: '',
    type: 'hive',
    display_name: '',
    host: 'localhost',
    port: 10000,
    username: 'hive',
    password: '',
    database: 'default',
    auth: 'NONE',
  };

  ngOnInit(): void {
    this.load();
    this.loadRuns();
    this.connectorService.load();
  }

  load(): void {
    this.api.getConnectors().subscribe((res) => {
      this.connectors.set(res.connectors as ConnectorInfo[]);
      this.defaultId.set(res.default);
    });
  }

  loadRuns(): void {
    this.api.listSyncRuns().subscribe((runs) => this.syncRuns.set(runs));
  }

  openNewForm(): void {
    this.editingId.set(null);
    this.form = {
      id: '',
      type: 'hive',
      display_name: 'New Hive connection',
      host: 'localhost',
      port: 10000,
      username: 'hive',
      password: '',
      database: 'default',
      auth: 'NONE',
    };
    this.showForm.set(true);
  }

  openEditForm(connector: ConnectorInfo): void {
    this.editingId.set(connector.id);
    this.form = {
      id: connector.id,
      type: String(connector.type ?? 'hive'),
      display_name: String(connector.display_name ?? connector.id),
      host: String(connector.host ?? 'localhost'),
      port: Number(connector.port ?? 10000),
      username: String(connector['username'] ?? 'hive'),
      password: '',
      database: String(connector.database ?? 'default'),
      auth: String(connector['auth'] ?? 'NONE'),
    };
    this.showForm.set(true);
  }

  cancelForm(): void {
    this.showForm.set(false);
    this.editingId.set(null);
  }

  saveConnector(): void {
    const id = this.form.id.trim();
    if (!id) return;
    this.saving.set(true);
    this.api.upsertConnector({ ...this.form, id }).subscribe({
      next: () => {
        this.saving.set(false);
        this.showForm.set(false);
        this.load();
        this.connectorService.load();
      },
      error: () => this.saving.set(false),
    });
  }

  setDefault(connectorId: string): void {
    this.connectorService.setDefault(connectorId);
    setTimeout(() => this.load(), 300);
  }

  test(connectorId: string): void {
    this.testing.set(connectorId);
    this.api.testConnector(connectorId).subscribe({
      next: (result) => {
        this.testResults.update((r) => ({ ...r, [connectorId]: result }));
        this.testing.set(null);
      },
      error: (err) => {
        this.testResults.update((r) => ({
          ...r,
          [connectorId]: { ok: false, message: err?.error?.message ?? 'Test failed', latency_ms: 0 },
        }));
        this.testing.set(null);
      },
    });
  }

  triggerSync(mode: 'full' | 'incremental', connectorId?: string): void {
    this.syncing.set(true);
    this.syncConnectorId.set(connectorId ?? null);
    this.api.triggerSync(mode, connectorId).subscribe({
      next: () => {
        this.syncing.set(false);
        this.syncConnectorId.set(null);
        setTimeout(() => this.loadRuns(), 1500);
      },
      error: () => {
        this.syncing.set(false);
        this.syncConnectorId.set(null);
      },
    });
  }

  triggerEnrichment(): void {
    this.enriching.set(true);
    this.api.triggerEnrichment().subscribe({
      next: () => this.enriching.set(false),
      error: () => this.enriching.set(false),
    });
  }
}
