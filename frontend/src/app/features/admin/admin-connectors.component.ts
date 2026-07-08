import { DatePipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { ApiService } from '../../core/api.service';
import { SyncRun } from '../../core/models';

interface ConnectorInfo {
  id: string;
  type: string;
  display_name?: string;
  host?: string;
  port?: number;
  database?: string;
  [key: string]: unknown;
}

@Component({
  selector: 'bl-admin-connectors',
  imports: [DatePipe, MatIconModule],
  templateUrl: './admin-connectors.component.html',
  styleUrl: './admin-connectors.component.scss',
})
export class AdminConnectorsComponent implements OnInit {
  private api = inject(ApiService);

  readonly connectors = signal<ConnectorInfo[]>([]);
  readonly defaultId = signal<string>('');
  readonly testResults = signal<Record<string, { ok: boolean; message: string; latency_ms: number }>>({});
  readonly testing = signal<string | null>(null);
  readonly syncRuns = signal<SyncRun[]>([]);
  readonly syncing = signal(false);
  readonly enriching = signal(false);

  ngOnInit(): void {
    this.load();
    this.loadRuns();
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

  triggerSync(mode: 'full' | 'incremental'): void {
    this.syncing.set(true);
    this.api.triggerSync(mode).subscribe({
      next: () => {
        this.syncing.set(false);
        setTimeout(() => this.loadRuns(), 1500);
      },
      error: () => this.syncing.set(false),
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
