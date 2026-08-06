import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { ApiService } from '../../core/api.service';
import { Abbreviation, BusinessRule, BusinessTerm, GlossaryTerm } from '../../core/models';

const EMPTY_TERM: GlossaryTerm = {
  term: '', definition: '', business_meaning: '', examples: [], owner: '', tags: [], synonyms: [],
};

const EMPTY_BUSINESS_TERM: BusinessTerm = {
  term: '', entity: '', column_name: '', value: '',
};

const EMPTY_ABBREVIATION: Abbreviation = {
  abbreviation: '', entity: '', value: '', description: '',
};

const EMPTY_BUSINESS_RULE: BusinessRule = {
  name: '', scope: 'global', entity: '', column_name: '', rule_type: '', statement: '',
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
  readonly businessTerms = signal<BusinessTerm[]>([]);
  readonly abbreviations = signal<Abbreviation[]>([]);
  readonly businessRules = signal<BusinessRule[]>([]);
  readonly search = signal('');
  readonly editing = signal<GlossaryTerm | null>(null);
  readonly editingBusiness = signal<BusinessTerm | null>(null);
  readonly editingAbbreviation = signal<Abbreviation | null>(null);
  readonly editingRule = signal<BusinessRule | null>(null);
  readonly activeSection = signal<'definitions' | 'bindings' | 'abbreviations' | 'rules'>('definitions');
  synonymsText = '';
  tagsText = '';

  readonly sections = [
    { id: 'definitions' as const, label: 'Definitions', count: () => this.terms().length },
    { id: 'bindings' as const, label: 'Bindings', count: () => this.businessTerms().length },
    { id: 'abbreviations' as const, label: 'Abbreviations', count: () => this.abbreviations().length },
    { id: 'rules' as const, label: 'Business rules', count: () => this.businessRules().length },
  ];

  ngOnInit(): void {
    this.reloadAll();
  }

  reloadAll(): void {
    const q = this.search() || undefined;
    this.api.listGlossary(q).subscribe((terms) => this.terms.set(terms));
    this.api.listBusinessTerms(q).subscribe((terms) => this.businessTerms.set(terms));
    this.api.listAbbreviations(q).subscribe((rows) => this.abbreviations.set(rows));
    this.api.listBusinessRules(q).subscribe((rows) => this.businessRules.set(rows));
  }

  onSearch(value: string): void {
    this.search.set(value);
    this.reloadAll();
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
      this.reloadAll();
    });
  }

  remove(term: GlossaryTerm): void {
    if (!term.id) return;
    this.api.deleteTerm(term.id).subscribe(() => this.reloadAll());
  }

  startNewBusiness(): void {
    this.editingBusiness.set({ ...EMPTY_BUSINESS_TERM });
  }

  startEditBusiness(term: BusinessTerm): void {
    this.editingBusiness.set({ ...term });
  }

  cancelBusiness(): void {
    this.editingBusiness.set(null);
  }

  saveBusiness(): void {
    const term = this.editingBusiness();
    if (!term || !term.term.trim() || !term.entity.trim() || !term.column_name.trim() || !term.value.trim()) return;
    const request = term.id
      ? this.api.updateBusinessTerm(term.id, term)
      : this.api.createBusinessTerm(term);
    request.subscribe(() => {
      this.editingBusiness.set(null);
      this.reloadAll();
    });
  }

  removeBusiness(term: BusinessTerm): void {
    if (!term.id) return;
    this.api.deleteBusinessTerm(term.id).subscribe(() => this.reloadAll());
  }

  startNewAbbreviation(): void {
    this.editingAbbreviation.set({ ...EMPTY_ABBREVIATION });
  }

  startEditAbbreviation(row: Abbreviation): void {
    this.editingAbbreviation.set({ ...row });
  }

  cancelAbbreviation(): void {
    this.editingAbbreviation.set(null);
  }

  saveAbbreviation(): void {
    const row = this.editingAbbreviation();
    if (!row || !row.abbreviation.trim() || !row.entity.trim() || !row.value.trim()) return;
    const request = row.id
      ? this.api.updateAbbreviation(row.id, row)
      : this.api.createAbbreviation(row);
    request.subscribe(() => {
      this.editingAbbreviation.set(null);
      this.reloadAll();
    });
  }

  removeAbbreviation(row: Abbreviation): void {
    if (!row.id) return;
    this.api.deleteAbbreviation(row.id).subscribe(() => this.reloadAll());
  }

  startNewRule(): void {
    this.editingRule.set({ ...EMPTY_BUSINESS_RULE });
  }

  startEditRule(rule: BusinessRule): void {
    this.editingRule.set({ ...rule });
  }

  cancelRule(): void {
    this.editingRule.set(null);
  }

  saveRule(): void {
    const rule = this.editingRule();
    if (!rule || !rule.name.trim() || !rule.statement.trim()) return;
    if (rule.scope !== 'global' && !rule.entity?.trim()) return;
    const request = rule.id ? this.api.updateBusinessRule(rule.id, rule) : this.api.createBusinessRule(rule);
    request.subscribe(() => {
      this.editingRule.set(null);
      this.reloadAll();
    });
  }

  removeRule(rule: BusinessRule): void {
    if (!rule.id) return;
    this.api.deleteBusinessRule(rule.id).subscribe(() => this.reloadAll());
  }
}
