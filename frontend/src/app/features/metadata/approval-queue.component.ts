import { Component, OnInit, inject, signal } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { ApiService } from '../../core/api.service';
import { ApprovalItem } from '../../core/models';

@Component({
  selector: 'bl-approval-queue',
  imports: [MatIconModule, MatTooltipModule],
  templateUrl: './approval-queue.component.html',
  styleUrl: './approval-queue.component.scss',
})
export class ApprovalQueueComponent implements OnInit {
  private api = inject(ApiService);

  readonly items = signal<ApprovalItem[]>([]);
  readonly selected = signal<Set<string>>(new Set());
  readonly loading = signal(false);
  readonly filterType = signal<string | null>(null);

  readonly entityTypes = [
    'table_description', 'column_description', 'tag', 'classification', 'glossary_term',
  ];

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.loading.set(true);
    this.api.listApprovals('pending', this.filterType() ?? undefined).subscribe({
      next: (items) => {
        this.items.set(items);
        this.selected.set(new Set());
        this.loading.set(false);
      },
      error: () => this.loading.set(false),
    });
  }

  setFilter(type: string | null): void {
    this.filterType.set(type);
    this.load();
  }

  toggle(id: string): void {
    const set = new Set(this.selected());
    set.has(id) ? set.delete(id) : set.add(id);
    this.selected.set(set);
  }

  toggleAll(): void {
    const all = this.items();
    this.selected.set(this.selected().size === all.length ? new Set() : new Set(all.map((i) => i.id)));
  }

  decide(item: ApprovalItem, action: 'approve' | 'reject'): void {
    this.api.decideApproval(item.id, action).subscribe(() => this.load());
  }

  bulkDecide(action: 'approve' | 'reject'): void {
    const ids = [...this.selected()];
    if (!ids.length) return;
    this.api.bulkDecide(ids, action).subscribe(() => this.load());
  }

  formatType(type: string): string {
    return type.replace(/_/g, ' ');
  }
}
