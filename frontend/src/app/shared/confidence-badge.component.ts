import { Component, computed, input } from '@angular/core';
import { MatTooltipModule } from '@angular/material/tooltip';
import { ConfidenceBreakdown } from '../core/models';

@Component({
  selector: 'bl-confidence',
  imports: [MatTooltipModule],
  template: `
    <span
      class="chip"
      [class.good]="level() === 'high'"
      [class.warn]="level() === 'medium'"
      [class.bad]="level() === 'low'"
      [matTooltip]="tooltip()"
    >
      {{ (confidence().overall * 100).toFixed(0) }}% confidence
    </span>
  `,
})
export class ConfidenceBadgeComponent {
  readonly confidence = input.required<ConfidenceBreakdown>();

  readonly level = computed(() => {
    const overall = this.confidence().overall;
    return overall >= 0.8 ? 'high' : overall >= 0.6 ? 'medium' : 'low';
  });

  readonly tooltip = computed(() => {
    const c = this.confidence();
    return (
      `Business ${(c.business * 100).toFixed(0)}% · ` +
      `Metadata ${(c.metadata * 100).toFixed(0)}% · ` +
      `SQL ${(c.sql * 100).toFixed(0)}%`
    );
  });
}
