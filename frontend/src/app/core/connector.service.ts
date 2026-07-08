import { Injectable, computed, inject, signal } from '@angular/core';
import { ApiService } from './api.service';

export interface ConnectorInfo {
  id: string;
  type: string;
  display_name?: string;
  host?: string;
  port?: number;
  database?: string;
  [key: string]: unknown;
}

const STORAGE_KEY = 'beeline.active_connector';

/** Tracks configured analytics connectors and the active default. */
@Injectable({ providedIn: 'root' })
export class ConnectorService {
  private api = inject(ApiService);

  readonly connectors = signal<ConnectorInfo[]>([]);
  readonly defaultId = signal<string>('hive');
  readonly activeId = signal<string>(localStorage.getItem(STORAGE_KEY) ?? 'hive');

  readonly activeConnector = computed(
    () => this.connectors().find((c) => c.id === this.activeId()) ?? null,
  );

  load(): void {
    this.api.getConnectors().subscribe((res) => {
      this.connectors.set(res.connectors as ConnectorInfo[]);
      this.defaultId.set(res.default);
      const stored = localStorage.getItem(STORAGE_KEY);
      if (!stored || !res.connectors.some((c) => (c as ConnectorInfo).id === stored)) {
        this.setActive(res.default);
      }
    });
  }

  setActive(connectorId: string): void {
    this.activeId.set(connectorId);
    localStorage.setItem(STORAGE_KEY, connectorId);
  }

  setDefault(connectorId: string): void {
    this.api.setDefaultConnector(connectorId).subscribe(() => {
      this.defaultId.set(connectorId);
      this.setActive(connectorId);
      this.load();
    });
  }
}
