import { Injectable, signal } from '@angular/core';

export interface Toast {
  id: number;
  kind: 'error' | 'success' | 'info';
  title: string;
  detail?: string;
}

/** Global toast queue so failures and confirmations are always surfaced to the user. */
@Injectable({ providedIn: 'root' })
export class NotificationService {
  private nextId = 1;
  readonly toasts = signal<Toast[]>([]);

  error(title: string, detail?: string): void {
    this.push('error', title, detail, 8000);
  }

  success(title: string, detail?: string): void {
    this.push('success', title, detail, 4000);
  }

  info(title: string, detail?: string): void {
    this.push('info', title, detail, 5000);
  }

  dismiss(id: number): void {
    this.toasts.update((list) => list.filter((t) => t.id !== id));
  }

  private push(kind: Toast['kind'], title: string, detail: string | undefined, ttlMs: number): void {
    const toast: Toast = { id: this.nextId++, kind, title, detail };
    this.toasts.update((list) => [...list.slice(-4), toast]);
    setTimeout(() => this.dismiss(toast.id), ttlMs);
  }
}
