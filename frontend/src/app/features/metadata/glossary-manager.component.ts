import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { ApiService } from '../../core/api.service';
import { GlossaryTerm } from '../../core/models';

const EMPTY_TERM: GlossaryTerm = {
  term: '', definition: '', business_meaning: '', examples: [], owner: '', tags: [], synonyms: [],
};

@Component({
  selector: 'bl-glossary-manager',
  imports: [FormsModule, MatIconModule],
  templateUrl: './glossary-manager.component.html',
  styleUrl: './glossary-manager.component.scss',
})
export class GlossaryManagerComponent implements OnInit {
  private api = inject(ApiService);

  readonly terms = signal<GlossaryTerm[]>([]);
  readonly search = signal('');
  readonly editing = signal<GlossaryTerm | null>(null);
  synonymsText = '';
  tagsText = '';

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.api.listGlossary(this.search() || undefined).subscribe((terms) => this.terms.set(terms));
  }

  onSearch(value: string): void {
    this.search.set(value);
    this.load();
  }

  startNew(): void {
    this.editing.set({ ...EMPTY_TERM });
    this.synonymsText = '';
    this.tagsText = '';
  }

  startEdit(term: GlossaryTerm): void {
    this.editing.set({ ...term });
    this.synonymsText = term.synonyms.join(', ');
    this.tagsText = term.tags.join(', ');
  }

  cancel(): void {
    this.editing.set(null);
  }

  save(): void {
    const term = this.editing();
    if (!term || !term.term.trim() || !term.definition.trim()) return;
    const payload: GlossaryTerm = {
      ...term,
      synonyms: this.synonymsText.split(',').map((s) => s.trim()).filter(Boolean),
      tags: this.tagsText.split(',').map((s) => s.trim()).filter(Boolean),
    };
    const request = term.id ? this.api.updateTerm(term.id, payload) : this.api.createTerm(payload);
    request.subscribe(() => {
      this.editing.set(null);
      this.load();
    });
  }

  remove(term: GlossaryTerm): void {
    if (!term.id) return;
    this.api.deleteTerm(term.id).subscribe(() => this.load());
  }
}
