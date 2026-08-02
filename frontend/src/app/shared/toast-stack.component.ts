import { Component, inject } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { NotificationService } from '../core/notification.service';

@Component({
  selector: 'bl-toast-stack',
  imports: [MatIconModule],
  template: `
    <div class="toast-stack" role="status" aria-live="polite">
      @for (toast of notifications.toasts(); track toast.id) {
        <div class="toast" [class]="'toast ' + toast.kind">
          <mat-icon class="toast-icon">
            {{ toast.kind === 'error' ? 'error_outline' : toast.kind === 'success' ? 'check_circle' : 'info' }}
          </mat-icon>
          <div class="toast-body">
            <div class="toast-title">{{ toast.title }}</div>
            @if (toast.detail) {
              <div class="toast-detail">{{ toast.detail }}</div>
            }
          </div>
          <button class="toast-close" (click)="notifications.dismiss(toast.id)" aria-label="Dismiss">
            <mat-icon>close</mat-icon>
          </button>
        </div>
      }
    </div>
  `,
  styles: `
    .toast-stack {
      position: fixed;
      right: 20px;
      bottom: 20px;
      display: flex;
      flex-direction: column;
      gap: 10px;
      z-index: 11000;
      max-width: 420px;
    }

    .toast {
      display: flex;
      align-items: flex-start;
      gap: 10px;
      padding: 12px 14px;
      border-radius: 12px;
      border: 1px solid var(--bl-border);
      background: var(--bl-surface-solid);
      box-shadow: var(--bl-shadow);
      animation: toast-in 0.18s ease-out;
    }

    @keyframes toast-in {
      from { opacity: 0; transform: translateY(8px); }
      to { opacity: 1; transform: translateY(0); }
    }

    .toast-icon { flex-shrink: 0; font-size: 20px; width: 20px; height: 20px; }
    .toast.error .toast-icon { color: var(--bl-bad); }
    .toast.success .toast-icon { color: var(--bl-good); }
    .toast.info .toast-icon { color: var(--bl-accent); }

    .toast-body { flex: 1; min-width: 0; }
    .toast-title { font-weight: 600; font-size: 13.5px; color: var(--bl-text); }
    .toast-detail {
      margin-top: 2px;
      font-size: 12.5px;
      color: var(--bl-text-muted);
      word-break: break-word;
      max-height: 80px;
      overflow: hidden;
    }

    .toast-close {
      flex-shrink: 0;
      border: none;
      background: transparent;
      color: var(--bl-text-muted);
      cursor: pointer;
      padding: 0;
      display: inline-flex;
    }
    .toast-close mat-icon { font-size: 16px; width: 16px; height: 16px; }
  `,
})
export class ToastStackComponent {
  readonly notifications = inject(NotificationService);
}
