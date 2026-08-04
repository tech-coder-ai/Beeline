import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { ApiService } from '../../core/api.service';

type ImportType = 'auto' | 'metadata' | 'synonyms' | 'business_terms' | 'abbreviations';

interface ImportChange {
  entity_type?: string;
  label?: string;
  entity?: string;
  field: string;
  current?: string | null;
  proposed?: string;
  value?: string;
}

interface PreviewResult {
  import_type?: string;
  matched_rows: number;
  unmatched: { row: number; reason: string }[];
  changes: ImportChange[];
  applied?: number;
  queued_for_approval?: number;
}

const IMPORT_HINTS: Record<ImportType, string> = {
  auto: 'Auto-detect from column headers',
  metadata: 'database, table, column, description, glossary, owner, tags, classification',
  synonyms: 'canonical, synonym (or canonical, synonyms with comma-separated values)',
  business_terms: 'term, entity, column_name, value',
  abbreviations: 'abbreviation, entity, value (optional: description)',
};

@Component({
  selector: 'bl-import-panel',
  imports: [FormsModule, MatIconModule],
  templateUrl: './import-panel.component.html',
  styleUrl: './import-panel.component.scss',
})
export class ImportPanelComponent {
  private api = inject(ApiService);

  readonly importType = signal<ImportType>('auto');
  readonly file = signal<File | null>(null);
  readonly preview = signal<PreviewResult | null>(null);
  readonly loading = signal(false);
  readonly committed = signal(false);

  readonly columnHint = computed(() => IMPORT_HINTS[this.importType()]);
  readonly isSemanticImport = computed(() => {
    const type = this.preview()?.import_type ?? this.importType();
    return type !== 'metadata' && type !== 'auto';
  });

  onTypeChange(value: ImportType): void {
    this.importType.set(value);
    this.preview.set(null);
    this.committed.set(false);
    const file = this.file();
    if (file) this.runPreview(file);
  }

  onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0] ?? null;
    this.file.set(file);
    this.preview.set(null);
    this.committed.set(false);
    if (file) this.runPreview(file);
  }

  runPreview(file: File): void {
    this.loading.set(true);
    const type = this.importType();
    this.api.importPreview(file, type === 'auto' ? undefined : type).subscribe({
      next: (result) => {
        this.preview.set(result as unknown as PreviewResult);
        this.loading.set(false);
      },
      error: () => this.loading.set(false),
    });
  }

  commit(): void {
    const file = this.file();
    if (!file) return;
    this.loading.set(true);
    const type = this.importType();
    this.api.importCommit(file, type === 'auto' ? undefined : type).subscribe({
      next: (result) => {
        this.preview.set(result as unknown as PreviewResult);
        this.committed.set(true);
        this.loading.set(false);
      },
      error: () => this.loading.set(false),
    });
  }

  reset(): void {
    this.file.set(null);
    this.preview.set(null);
    this.committed.set(false);
  }
}
