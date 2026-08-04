import { Injectable, computed, inject, signal } from '@angular/core';
import { ApiService } from './api.service';

export type FeatureFlagName =
  | 'dashboards'
  | 'metadata_manager'
  | 'saved_queries'
  | 'approvals'
  | 'csv_import'
  | 'explain_sql'
  | 'feedback'
  | 'debug_mode';

const DEFAULT_FLAGS: Record<FeatureFlagName, boolean> = {
  dashboards: true,
  metadata_manager: true,
  saved_queries: true,
  approvals: true,
  csv_import: true,
  explain_sql: true,
  feedback: true,
  debug_mode: false,
};

@Injectable({ providedIn: 'root' })
export class FeatureFlagService {
  private api = inject(ApiService);

  private readonly _flags = signal<Record<string, boolean>>({ ...DEFAULT_FLAGS });

  readonly flags = this._flags.asReadonly();

  readonly dashboards = computed(() => this.isEnabled('dashboards'));
  readonly metadataManager = computed(() => this.isEnabled('metadata_manager'));
  readonly savedQueries = computed(() => this.isEnabled('saved_queries'));
  readonly approvals = computed(() => this.isEnabled('approvals'));
  readonly csvImport = computed(() => this.isEnabled('csv_import'));
  readonly explainSql = computed(() => this.isEnabled('explain_sql'));
  readonly feedback = computed(() => this.isEnabled('feedback'));
  readonly debugMode = computed(() => this.isEnabled('debug_mode'));

  constructor() {
    this.refresh();
  }

  refresh(): void {
    this.api.getFeatureFlags().subscribe({
      next: (flags) => this._flags.set({ ...DEFAULT_FLAGS, ...flags }),
      error: () => this._flags.set({ ...DEFAULT_FLAGS }),
    });
  }

  isEnabled(name: FeatureFlagName | string): boolean {
    const value = this._flags()[name];
    return value !== false;
  }
}
