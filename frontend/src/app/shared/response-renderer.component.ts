import { DecimalPipe } from '@angular/common';
import { Component, inject, input, output } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { ApiService } from '../core/api.service';
import { BeelineResponse, ClarificationOption } from '../core/models';
import { ChartComponent } from './chart.component';
import { ConfidenceBadgeComponent } from './confidence-badge.component';
import { DataGridComponent } from './data-grid.component';
import { KpiCardsComponent } from './kpi-cards.component';
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
    FormsModule, DecimalPipe, MatIconModule, MatTooltipModule, ChartComponent, KpiCardsComponent,
    DataGridComponent, SqlPanelComponent, ConfidenceBadgeComponent,
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

  private api = inject(ApiService);
  feedbackGiven: 'up' | 'down' | null = null;
  showSql = false;
  clarificationText = '';

  vote(rating: 'up' | 'down'): void {
    const r = this.response();
    this.feedbackGiven = rating;
    this.api.submitFeedback({ execution_id: r.execution_id, rating }).subscribe();
  }

  toggleSql(): void {
    this.showSql = !this.showSql;
  }

  submitClarificationText(): void {
    if (this.clarificationText.trim()) {
      this.clarify.emit(this.clarificationText.trim());
      this.clarificationText = '';
    }
  }
}
