import { Component, inject, signal } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { ApiService } from '../../core/api.service';

interface ImportChange {
  entity_type: string;
  label: string;
  field: string;
  current: string | null;
  proposed: string;
}

interface PreviewResult {
  matched_rows: number;
  unmatched: { row: number; reason: string }[];
  changes: ImportChange[];
}

@Component({
  selector: 'bl-import-panel',
  imports: [MatIconModule],
  templateUrl: './import-panel.component.html',
  styleUrl: './import-panel.component.scss',
})
export class ImportPanelComponent {
  private api = inject(ApiService);

  readonly file = signal<File | null>(null);
  readonly preview = signal<PreviewResult | null>(null);
  readonly loading = signal(false);
  readonly committed = signal(false);

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
    this.api.importPreview(file).subscribe({
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
    this.api.importCommit(file).subscribe({
      next: () => {
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
