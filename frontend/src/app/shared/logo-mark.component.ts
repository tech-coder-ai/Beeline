import { Component, input } from '@angular/core';

/** DataLens brand mark: a lens over an ascending bar chart. Used in the nav rail and chat welcome. */
@Component({
  selector: 'bl-logo-mark',
  template: `
    <svg
      [attr.width]="size()"
      [attr.height]="size()"
      viewBox="0 0 24 24"
      xmlns="http://www.w3.org/2000/svg"
    >
      <rect x="6.8" y="11" width="2" height="3.3" rx="0.4" class="bar" />
      <rect x="9.6" y="8.5" width="2" height="5.8" rx="0.4" class="bar" />
      <rect x="12.4" y="6" width="2" height="8.3" rx="0.4" class="bar" />
      <circle cx="10" cy="10" r="6.5" fill="none" class="ring" stroke-width="1.7" />
      <line x1="14.6" y1="14.6" x2="19.4" y2="19.4" class="ring" stroke-width="2.4" stroke-linecap="round" />
    </svg>
  `,
  styles: [`
    :host { display: inline-flex; }
    .bar { fill: var(--bl-accent); }
    .ring { stroke: var(--bl-text); }
  `],
})
export class LogoMarkComponent {
  readonly size = input(28);
}
