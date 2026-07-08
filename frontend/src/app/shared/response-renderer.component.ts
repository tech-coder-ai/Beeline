import { DecimalPipe } from '@angular/common';
import { Component, inject, input, output } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { ApiService } from '../core/api.service';
import { ConnectorService } from '../core/connector.service';
import { FeatureFlagService } from '../core/feature-flags.service';
import { BeelineResponse, ClarificationOption, SqlExplanation } from '../core/models';
import { ConfidenceBadgeComponent } from './confidence-badge.component';
import { KpiCardsComponent } from './kpi-cards.component';
import { ResultDataViewComponent } from './result-data-view.component';
import { SqlPanelComponent } from './sql-panel.component';

/**
 * Adaptive Response Renderer.
 * Reads the BeelineResponse.visualization field and composes the layout:
 * KPIs -> charts -> grid -> insights -> recommendations -> follow-ups.
 * Angular decides how to render; the backend never sends HTML/markdown tables.
 */
@Component({
  selector: 'bl-response-renderer',
  imports: [
    FormsModule, DecimalPipe, MatIconModule, MatTooltipModule, KpiCardsComponent,
    SqlPanelComponent, ConfidenceBadgeComponent, ResultDataViewComponent,
  ],
  templateUrl: './response-renderer.component.html',
  styleUrl: './response-renderer.component.scss',
})
export class ResponseRendererComponent {
  readonly response = input.required<BeelineResponse>();
  readonly compact = input(false);

  readonly clarify = output<ClarificationOption | string>();
  readonly executePreview = output<void>();
  readonly refineQuestion = output<void>();
  readonly followUp = output<string>();
  readonly saveQuery = output<void>();
  readonly pinToDashboard = output<void>();
  readonly inspect = output<void>();

  private api = inject(ApiService);
  private connectors = inject(ConnectorService);
  readonly flags = inject(FeatureFlagService);
  feedbackGiven: 'up' | 'down' | null = null;
  showSql = false;
  showExplain = false;
  explainLoading = false;
  loadedExplanation: SqlExplanation | null = null;
  clarificationText = '';

  vote(rating: 'up' | 'down'): void {
    const r = this.response();
    this.feedbackGiven = rating;
    this.api.submitFeedback({ execution_id: r.execution_id, rating }).subscribe();
  }

  toggleSql(): void {
    this.showSql = !this.showSql;
  }

  toggleExplain(): void {
    const r = this.response();
    if (r.sql_explanation) {
      this.showExplain = !this.showExplain;
      return;
    }
    if (this.loadedExplanation) {
      this.showExplain = !this.showExplain;
      return;
    }
    if (!r.sql) return;
    this.explainLoading = true;
    const question = (r.metadata?.['refined_prompt'] as string) ?? r.summary;
    this.api.explainSql(r.sql, this.connectors.activeId(), question).subscribe({
      next: (exp) => {
        this.loadedExplanation = exp;
        this.showExplain = true;
        this.explainLoading = false;
      },
      error: () => {
        this.explainLoading = false;
      },
    });
  }

  activeExplanation(): SqlExplanation | null {
    return this.response().sql_explanation ?? this.loadedExplanation;
  }

  submitClarificationText(): void {
    if (this.clarificationText.trim()) {
      this.clarify.emit(this.clarificationText.trim());
      this.clarificationText = '';
    }
  }
}
