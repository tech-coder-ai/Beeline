import { DecimalPipe } from '@angular/common';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { ApiService } from '../../core/api.service';
import { NotificationService } from '../../core/notification.service';
import { CatalogColumn, CatalogDatabase, CatalogRelationship, CatalogTable } from '../../core/models';

interface GlossaryHintDraft {
  term: string;
  definition: string;
}

interface ColumnDraft {
  description: string;
  tags: string;
  classification: string;
  is_pii: boolean;
}

const CLASSIFICATIONS = ['', 'public', 'internal', 'confidential', 'pii'];
const RELATIONSHIP_TYPES = [
  { value: 'many_to_one', label: 'Many → one' },
  { value: 'one_to_many', label: 'One → many' },
  { value: 'one_to_one', label: 'One → one' },
  { value: 'many_to_many', label: 'Many → many' },
];
const JOIN_TYPES = ['inner', 'left', 'right', 'full'];

@Component({
  selector: 'bl-catalog-browser',
  imports: [FormsModule, DecimalPipe, MatIconModule, MatTooltipModule],
  templateUrl: './catalog-browser.component.html',
  styleUrl: './catalog-browser.component.scss',
})
export class CatalogBrowserComponent implements OnInit {
  private api = inject(ApiService);
  private notifications = inject(NotificationService);

  readonly classifications = CLASSIFICATIONS;
  readonly relationshipTypes = RELATIONSHIP_TYPES;
  readonly joinTypes = JOIN_TYPES;
  readonly databases = signal<CatalogDatabase[]>([]);
  readonly tables = signal<CatalogTable[]>([]);
  readonly allTables = signal<CatalogTable[]>([]);
  readonly relationships = signal<CatalogRelationship[]>([]);
  readonly search = signal('');
  readonly selectedDb = signal<string | null>(null);
  readonly selectedTable = signal<CatalogTable | null>(null);
  readonly loading = signal(false);
  readonly editingTable = signal(false);
  readonly savingTable = signal(false);
  readonly editingColumnId = signal<string | null>(null);
  readonly savingColumn = signal(false);
  readonly enriching = signal(false);
  readonly enrichMessage = signal<string | null>(null);
  readonly showRelForm = signal(false);
  readonly savingRel = signal(false);
  readonly targetTable = signal<CatalogTable | null>(null);

  descriptionDraft = '';
  ownerDraft = '';
  stewardDraft = '';
  classificationDraft = '';
  tagsDraft = '';
  columnDraft: ColumnDraft = { description: '', tags: '', classification: '', is_pii: false };
  glossaryHints: GlossaryHintDraft[] = [{ term: '', definition: '' }];
  refreshRowCount = true;
  relToTableId = '';
  relFromColumns: string[] = [];
  relToColumns: string[] = [];
  relType = 'many_to_one';
  relJoinType = 'inner';
  relDescription = '';

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
      this.resetTableDrafts(full);
      this.glossaryHints = [{ term: '', definition: '' }];
      this.refreshRowCount = full.row_count == null;
      this.enrichMessage.set(null);
      this.editingTable.set(false);
      this.editingColumnId.set(null);
      this.showRelForm.set(false);
      this.loadRelationships(full.id);
    });
  }

  closeDrawer(): void {
    this.selectedTable.set(null);
    this.enrichMessage.set(null);
    this.editingColumnId.set(null);
    this.editingTable.set(false);
    this.showRelForm.set(false);
    this.relationships.set([]);
  }

  loadRelationships(tableId: string): void {
    this.api.listRelationships(tableId).subscribe({
      next: (rows) => this.relationships.set(rows),
      error: () => this.relationships.set([]),
    });
  }

  startRelationshipForm(): void {
    const table = this.selectedTable();
    if (!table) return;
    this.showRelForm.set(true);
    this.relToTableId = '';
    this.relFromColumns = [];
    this.relToColumns = [];
    this.relType = 'many_to_one';
    this.relJoinType = 'inner';
    this.relDescription = '';
    this.targetTable.set(null);
    if (!this.allTables().length) {
      this.api.listTables().subscribe((rows) => this.allTables.set(rows.filter((t) => t.id !== table.id)));
    }
  }

  cancelRelationshipForm(): void {
    this.showRelForm.set(false);
  }

  onRelToTableChange(tableId: string): void {
    this.relToTableId = tableId;
    this.relToColumns = [];
    if (!tableId) {
      this.targetTable.set(null);
      return;
    }
    this.api.getTable(tableId).subscribe((full) => this.targetTable.set(full));
  }

  toggleRelFromColumn(name: string, checked: boolean): void {
    this.relFromColumns = checked
      ? [...this.relFromColumns, name]
      : this.relFromColumns.filter((c) => c !== name);
  }

  toggleRelToColumn(name: string, checked: boolean): void {
    this.relToColumns = checked
      ? [...this.relToColumns, name]
      : this.relToColumns.filter((c) => c !== name);
  }

  saveRelationship(): void {
    const table = this.selectedTable();
    if (!table || this.savingRel() || !this.relToTableId) return;
    if (!this.relFromColumns.length || !this.relToColumns.length) return;
    if (this.relFromColumns.length !== this.relToColumns.length) return;

    this.savingRel.set(true);
    this.api
      .createRelationship({
        from_table_id: table.id,
        to_table_id: this.relToTableId,
        from_columns: this.relFromColumns,
        to_columns: this.relToColumns,
        relationship_type: this.relType,
        join_type: this.relJoinType,
        description: this.relDescription.trim() || null,
      })
      .subscribe({
        next: () => {
          this.savingRel.set(false);
          this.showRelForm.set(false);
          this.loadRelationships(table.id);
          this.notifications.success('Relationship saved');
        },
        error: () => this.savingRel.set(false),
      });
  }

  deleteRelationship(rel: CatalogRelationship): void {
    const table = this.selectedTable();
    if (!table || !confirm('Delete this relationship?')) return;
    this.api.deleteRelationship(rel.id).subscribe({
      next: () => {
        this.loadRelationships(table.id);
        this.notifications.success('Relationship deleted');
      },
    });
  }

  relationshipSummary(rel: CatalogRelationship, currentTableId: string): string {
    const from =
      rel.from_table_id === currentTableId
        ? 'this table'
        : `${rel.from_database_name}.${rel.from_table_name}`;
    const to =
      rel.to_table_id === currentTableId
        ? 'this table'
        : `${rel.to_database_name}.${rel.to_table_name}`;
    const keys = rel.from_columns
      .map((c, i) => `${c} → ${rel.to_columns[i] ?? '?'}`)
      .join(', ');
    return `${from} → ${to}: ${keys}`;
  }

  relTableOptions(): CatalogTable[] {
    const table = this.selectedTable();
    const pool = this.allTables().length ? this.allTables() : this.tables();
    return pool.filter((t) => t.id !== table?.id);
  }

  private resetTableDrafts(table: CatalogTable): void {
    this.descriptionDraft = table.description ?? '';
    this.ownerDraft = table.owner ?? '';
    this.stewardDraft = table.steward ?? '';
    this.classificationDraft = table.classification ?? '';
    this.tagsDraft = (table.tags ?? []).join(', ');
  }

  startTableEdit(): void {
    const table = this.selectedTable();
    if (!table) return;
    this.resetTableDrafts(table);
    this.editingTable.set(true);
  }

  cancelTableEdit(): void {
    this.editingTable.set(false);
  }

  saveTable(): void {
    const table = this.selectedTable();
    if (!table || this.savingTable()) return;
    const tags = this.splitTags(this.tagsDraft);
    this.savingTable.set(true);
    this.api
      .updateTable(table.id, {
        description: this.descriptionDraft.trim() || null,
        owner: this.ownerDraft.trim() || null,
        steward: this.stewardDraft.trim() || null,
        classification: this.classificationDraft || null,
        tags,
      })
      .subscribe({
        next: () => {
          this.savingTable.set(false);
          this.editingTable.set(false);
          this.selectedTable.set({
            ...table,
            description: this.descriptionDraft.trim() || null,
            owner: this.ownerDraft.trim() || null,
            steward: this.stewardDraft.trim() || null,
            classification: this.classificationDraft || null,
            tags,
          });
          this.notifications.success('Table metadata saved', `${table.database_name}.${table.name}`);
          this.loadTables();
        },
        error: () => this.savingTable.set(false),
      });
  }

  startColumnEdit(column: CatalogColumn): void {
    this.editingColumnId.set(column.id);
    this.columnDraft = {
      description: column.description ?? '',
      tags: (column.tags ?? []).join(', '),
      classification: column.classification ?? '',
      is_pii: column.is_pii,
    };
  }

  cancelColumnEdit(): void {
    this.editingColumnId.set(null);
  }

  saveColumn(column: CatalogColumn): void {
    const table = this.selectedTable();
    if (!table || this.savingColumn()) return;
    const tags = this.splitTags(this.columnDraft.tags);
    const update = {
      description: this.columnDraft.description.trim() || null,
      tags,
      classification: this.columnDraft.classification || null,
      is_pii: this.columnDraft.is_pii,
    };
    this.savingColumn.set(true);
    this.api.updateColumn(column.id, update).subscribe({
      next: () => {
        this.savingColumn.set(false);
        this.editingColumnId.set(null);
        this.selectedTable.set({
          ...table,
          columns: (table.columns ?? []).map((c) =>
            c.id === column.id
              ? {
                  ...c,
                  description: update.description,
                  tags,
                  classification: update.classification,
                  is_pii: update.is_pii,
                }
              : c,
          ),
        });
        this.notifications.success('Column metadata saved', column.name);
      },
      error: () => this.savingColumn.set(false),
    });
  }

  private splitTags(raw: string): string[] {
    return raw
      .split(',')
      .map((t) => t.trim())
      .filter(Boolean);
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

    const tags = this.splitTags(this.tagsDraft);
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
            this.resetTableDrafts(full);
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
