import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { ApiService } from '../../core/api.service';
import { SavedQuery, SqlResult } from '../../core/models';
import { ChartComponent } from '../../shared/chart.component';
import { DataGridComponent } from '../../shared/data-grid.component';

@Component({
  selector: 'bl-queries-page',
  imports: [FormsModule, MatIconModule, MatTooltipModule, DataGridComponent, ChartComponent],
  templateUrl: './queries-page.component.html',
  styleUrl: './queries-page.component.scss',
})
export class QueriesPageComponent implements OnInit {
  private api = inject(ApiService);

  readonly queries = signal<SavedQuery[]>([]);
  readonly result = signal<SqlResult | null>(null);
  readonly runningId = signal<string | null>(null);
  readonly showBookmarkedOnly = signal(false);
  readonly editorSql = signal('');
  readonly editorResult = signal<SqlResult | null>(null);
  readonly running = signal(false);

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.api.listSavedQueries().subscribe((queries) => this.queries.set(queries));
  }

  get visibleQueries(): SavedQuery[] {
    return this.showBookmarkedOnly() ? this.queries().filter((q) => q.is_bookmarked) : this.queries();
  }

  run(query: SavedQuery): void {
    if (!query.id) return;
    this.runningId.set(query.id);
    this.api.runSavedQuery(query.id).subscribe({
      next: (result) => {
        this.result.set(result);
        this.runningId.set(null);
        this.load();
      },
      error: () => this.runningId.set(null),
    });
  }

  toggleBookmark(query: SavedQuery): void {
    if (!query.id) return;
    this.api.toggleBookmark(query.id).subscribe(() => this.load());
  }

  remove(query: SavedQuery): void {
    if (!query.id) return;
    this.api.deleteQuery(query.id).subscribe(() => {
      this.load();
      if (this.result()) this.result.set(null);
    });
  }

  runEditor(): void {
    const sql = this.editorSql().trim();
    if (!sql) return;
    this.running.set(true);
    this.api.executeSql(sql).subscribe({
      next: (result) => {
        this.editorResult.set(result);
        this.running.set(false);
      },
      error: () => this.running.set(false),
    });
  }

  saveFromEditor(): void {
    const sql = this.editorSql().trim();
    if (!sql) return;
    const name = prompt('Name this query') ?? '';
    if (!name.trim()) return;
    this.api.saveQuery({ name: name.trim(), sql, tags: [] }).subscribe(() => this.load());
  }
}
