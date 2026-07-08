import { DatePipe, KeyValuePipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { ApiService } from '../../core/api.service';
import { AuditLogEntry, ExecutionLog } from '../../core/models';

@Component({
  selector: 'bl-admin-logs',
  imports: [DatePipe, KeyValuePipe, FormsModule, MatIconModule, MatTooltipModule],
  templateUrl: './admin-logs.component.html',
  styleUrl: './admin-logs.component.scss',
})
export class AdminLogsComponent implements OnInit {
  private api = inject(ApiService);

  readonly executions = signal<ExecutionLog[]>([]);
  readonly audits = signal<AuditLogEntry[]>([]);
  readonly usage = signal<Record<string, unknown>>({});
  readonly search = signal('');
  readonly view = signal<'executions' | 'audit'>('executions');
  readonly confirmClear = signal(false);
  readonly clearing = signal(false);
  readonly clearMessage = signal<string | null>(null);

  ngOnInit(): void {
    this.load();
    this.loadUsage();
  }

  load(): void {
    this.api.executionLogs(this.search() || undefined).subscribe((e) => this.executions.set(e));
    this.api.auditLogs().subscribe((a) => this.audits.set(a));
  }

  loadUsage(): void {
    this.api.usageAnalytics().subscribe((u) => this.usage.set(u));
  }

  onSearch(value: string): void {
    this.search.set(value);
    this.load();
  }

  startClear(): void {
    this.clearMessage.set(null);
    this.confirmClear.set(true);
  }

  cancelClear(): void {
    this.confirmClear.set(false);
  }

  clearAll(): void {
    this.clearing.set(true);
    this.api.clearLogsAndAnalytics().subscribe({
      next: (result) => {
        const total = Object.values(result.deleted).reduce((sum, n) => sum + n, 0);
        this.clearMessage.set(`Cleared ${total} record(s).`);
        this.confirmClear.set(false);
        this.clearing.set(false);
        this.load();
        this.loadUsage();
      },
      error: () => {
        this.clearMessage.set('Failed to clear logs.');
        this.clearing.set(false);
      },
    });
  }

  get byStatus(): Record<string, unknown> {
    return (this.usage()['by_status'] as Record<string, unknown>) ?? {};
  }
}
