import { DatePipe, KeyValuePipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { ApiService } from '../../core/api.service';
import { AuditLogEntry, ExecutionLog } from '../../core/models';

@Component({
  selector: 'bl-admin-logs',
  imports: [DatePipe, KeyValuePipe, FormsModule, MatIconModule],
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

  ngOnInit(): void {
    this.load();
    this.api.usageAnalytics().subscribe((u) => this.usage.set(u));
  }

  load(): void {
    this.api.executionLogs(this.search() || undefined).subscribe((e) => this.executions.set(e));
    this.api.auditLogs().subscribe((a) => this.audits.set(a));
  }

  onSearch(value: string): void {
    this.search.set(value);
    this.load();
  }

  get byStatus(): Record<string, unknown> {
    return (this.usage()['by_status'] as Record<string, unknown>) ?? {};
  }
}
