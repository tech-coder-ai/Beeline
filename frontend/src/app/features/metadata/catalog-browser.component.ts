import { DecimalPipe } from '@angular/common';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { ApiService } from '../../core/api.service';
import { CatalogDatabase, CatalogTable } from '../../core/models';

interface GlossaryHintDraft {
  term: string;
  definition: string;
}

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
  readonly enriching = signal(false);
  readonly enrichMessage = signal<string | null>(null);
  descriptionDraft = '';
  tagsDraft = '';
  glossaryHints: GlossaryHintDraft[] = [{ term: '', definition: '' }];
  refreshRowCount = true;

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
      this.tagsDraft = (full.tags ?? []).join(', ');
      this.glossaryHints = [{ term: '', definition: '' }];
      this.refreshRowCount = full.row_count == null;
      this.enrichMessage.set(null);
      this.editingDescription.set(false);
    });
  }

  closeDrawer(): void {
    this.selectedTable.set(null);
    this.enrichMessage.set(null);
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

  addGlossaryHint(): void {
    this.glossaryHints = [...this.glossaryHints, { term: '', definition: '' }];
  }

  removeGlossaryHint(index: number): void {
    if (this.glossaryHints.length <= 1) {
      this.glossaryHints = [{ term: '', definition: '' }];
      return;
    }
    this.glossaryHints = this.glossaryHints.filter((_, i) => i !== index);
  }

  enrichSelectedTable(): void {
    const table = this.selectedTable();
    if (!table || this.enriching()) return;

    const tags = this.tagsDraft
      .split(',')
      .map((t) => t.trim())
      .filter(Boolean);
    const glossaryHints = this.glossaryHints
      .filter((h) => h.term.trim())
      .map((h) => ({ term: h.term.trim(), definition: h.definition.trim() || null }));

    this.enriching.set(true);
    this.enrichMessage.set(null);

    this.api
      .enrichTable(table.id, {
        description: this.descriptionDraft.trim() || null,
        tags: tags.length ? tags : undefined,
        glossary_hints: glossaryHints.length ? glossaryHints : undefined,
        refresh_row_count: this.refreshRowCount,
      })
      .subscribe({
        next: (result) => {
          this.enriching.set(false);
          const rowNote =
            result.row_count != null ? ` Row count: ${result.row_count.toLocaleString()}.` : '';
          this.enrichMessage.set(
            `Queued ${result.proposals} AI proposal${result.proposals === 1 ? '' : 's'} for approval.${rowNote}`,
          );
          this.api.getTable(table.id).subscribe((full) => {
            this.selectedTable.set(full);
            this.descriptionDraft = full.description ?? '';
            this.tagsDraft = (full.tags ?? []).join(', ');
          });
          this.loadTables();
        },
        error: (err) => {
          this.enriching.set(false);
          this.enrichMessage.set(err?.error?.message ?? 'Enrichment failed. Check LLM configuration.');
        },
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
