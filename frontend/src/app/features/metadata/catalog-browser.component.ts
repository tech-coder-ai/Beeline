import { DecimalPipe } from '@angular/common';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { ApiService } from '../../core/api.service';
import { CatalogDatabase, CatalogTable } from '../../core/models';

@Component({
  selector: 'bl-catalog-browser',
  imports: [FormsModule, DecimalPipe, MatIconModule],
  templateUrl: './catalog-browser.component.html',
  styleUrl: './catalog-browser.component.scss',
})
export class CatalogBrowserComponent implements OnInit {
  private api = inject(ApiService);

  readonly databases = signal<CatalogDatabase[]>([]);
  readonly tables = signal<CatalogTable[]>([]);
  readonly search = signal('');
  readonly selectedDb = signal<string | null>(null);
  readonly selectedTable = signal<CatalogTable | null>(null);
  readonly loading = signal(false);
  readonly editingDescription = signal(false);
  descriptionDraft = '';

  readonly filteredTables = computed(() => this.tables());

  ngOnInit(): void {
    this.api.listDatabases().subscribe((dbs) => this.databases.set(dbs));
    this.loadTables();
  }

  loadTables(): void {
    this.loading.set(true);
    this.api.listTables(this.selectedDb() ?? undefined, this.search() || undefined).subscribe({
      next: (tables) => {
        this.tables.set(tables);
        this.loading.set(false);
      },
      error: () => this.loading.set(false),
    });
  }

  onSearch(value: string): void {
    this.search.set(value);
    this.loadTables();
  }

  selectDb(id: string | null): void {
    this.selectedDb.set(id);
    this.loadTables();
  }

  openTable(table: CatalogTable): void {
    this.api.getTable(table.id).subscribe((full) => {
      this.selectedTable.set(full);
      this.descriptionDraft = full.description ?? '';
      this.editingDescription.set(false);
    });
  }

  closeDrawer(): void {
    this.selectedTable.set(null);
  }

  saveDescription(): void {
    const table = this.selectedTable();
    if (!table) return;
    this.api.updateTable(table.id, { description: this.descriptionDraft }).subscribe(() => {
      this.selectedTable.set({ ...table, description: this.descriptionDraft });
      this.editingDescription.set(false);
      this.loadTables();
    });
  }

  formatBytes(bytes?: number | null): string {
    if (!bytes) return '-';
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    let value = bytes;
    let i = 0;
    while (value >= 1024 && i < units.length - 1) {
      value /= 1024;
      i++;
    }
    return `${value.toFixed(1)} ${units[i]}`;
  }
}
