import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { ApiService } from '../../core/api.service';
import { FeatureFlagService } from '../../core/feature-flags.service';

interface ConfigNode {
  [key: string]: unknown;
}

@Component({
  selector: 'bl-admin-config',
  imports: [FormsModule, MatIconModule, MatSlideToggleModule],
  templateUrl: './admin-config.component.html',
  styleUrl: './admin-config.component.scss',
})
export class AdminConfigComponent implements OnInit {
  private api = inject(ApiService);
  private featureFlagsService = inject(FeatureFlagService);

  readonly config = signal<ConfigNode>({});
  readonly saved = signal(false);

  ngOnInit(): void {
    this.api.getConfig().subscribe((cfg) => this.config.set(cfg));
  }

  get pipeline(): ConfigNode {
    return (this.config()['pipeline'] as ConfigNode) ?? {};
  }
  get guardrails(): ConfigNode {
    return (this.config()['guardrails'] as ConfigNode) ?? {};
  }
  get cost(): ConfigNode {
    return (this.config()['cost'] as ConfigNode) ?? {};
  }
  get featureFlags(): ConfigNode {
    return (this.config()['feature_flags'] as ConfigNode) ?? {};
  }
  get confidence(): ConfigNode {
    return (this.pipeline['confidence'] as ConfigNode) ?? {};
  }
  get queryPreview(): ConfigNode {
    return (this.pipeline['query_preview'] as ConfigNode) ?? {};
  }
  get blockedKeywords(): string[] {
    return (this.guardrails['blocked_keywords'] as string[]) ?? [];
  }
  get flagKeys(): string[] {
    return ['dashboards', 'metadata_manager', 'saved_queries', 'approvals', 'csv_import', 'explain_sql', 'feedback'];
  }

  update(key: string, value: unknown): void {
    this.api.updateConfig(key, value).subscribe(() => {
      this.saved.set(true);
      if (key.startsWith('feature_flags.')) {
        this.featureFlagsService.refresh();
      }
      setTimeout(() => this.saved.set(false), 1200);
    });
  }

  toggleFlag(name: string, current: unknown): void {
    this.update(`feature_flags.${name}`, !current);
    (this.featureFlags as Record<string, unknown>)[name] = !current;
  }

  toggleManualReview(current: unknown): void {
    this.update('pipeline.query_preview.manual_review', !current);
    (this.queryPreview as Record<string, unknown>)['manual_review'] = !current;
  }

  numberFields = [
    { path: 'pipeline.confidence.clarification_threshold', label: 'Clarification threshold', get: () => this.confidence['clarification_threshold'] },
    { path: 'pipeline.confidence.autoexecute_threshold', label: 'Auto-execute threshold', get: () => this.confidence['autoexecute_threshold'] },
    { path: 'guardrails.max_result_rows', label: 'Max result rows', get: () => this.guardrails['max_result_rows'] },
    { path: 'guardrails.default_limit', label: 'Default LIMIT', get: () => this.guardrails['default_limit'] },
    { path: 'guardrails.query_timeout_seconds', label: 'Query timeout (s)', get: () => this.guardrails['query_timeout_seconds'] },
    { path: 'guardrails.max_joins', label: 'Max joins', get: () => this.guardrails['max_joins'] },
    { path: 'cost.max_estimated_rows_scanned', label: 'Max rows scanned (block)', get: () => this.cost['max_estimated_rows_scanned'] },
    { path: 'cost.max_estimated_runtime_seconds', label: 'Max runtime seconds (block)', get: () => this.cost['max_estimated_runtime_seconds'] },
  ];
}
