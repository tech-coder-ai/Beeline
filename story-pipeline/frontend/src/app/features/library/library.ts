import { DatePipe } from '@angular/common';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatExpansionModule } from '@angular/material/expansion';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatSelectModule } from '@angular/material/select';
import { Router } from '@angular/router';
import { Api } from '../../core/api.service';
import { Story } from '../../core/models';
import { StatusChip } from '../../shared/status-chip';

const ALL_USES = ['adaptation', 'verbatim', 'commercial', 'attribution_required', 'share_alike', 'non_commercial'];

@Component({
  selector: 'app-library',
  imports: [FormsModule, MatButtonModule, MatIconModule, MatFormFieldModule, MatInputModule, MatSelectModule,
            MatExpansionModule, MatProgressBarModule, StatusChip, DatePipe],
  template: `
    <div class="page-head">
      <div><h1>Story library</h1><div class="sub">Every candidate with its provenance. Nothing is usable until a person approves its rights.</div></div>
    </div>

    <mat-accordion class="lib-tools">
      <mat-expansion-panel>
        <mat-expansion-panel-header><mat-panel-title><mat-icon>travel_explore</mat-icon>&nbsp;Discover stories</mat-panel-title></mat-expansion-panel-header>
        <div class="row">
          <mat-form-field class="dense"><mat-label>Connector</mat-label>
            <mat-select [(ngModel)]="connector">@for (c of connectors(); track c) { <mat-option [value]="c">{{ c }}</mat-option> }</mat-select>
          </mat-form-field>
          <mat-form-field class="dense" style="flex:1; min-width:200px"><mat-label>Search (title, author, text)</mat-label>
            <input matInput [(ngModel)]="query" (keyup.enter)="discover()"></mat-form-field>
          <mat-form-field class="dense" style="width:90px"><mat-label>Limit</mat-label><input matInput type="number" [(ngModel)]="limit"></mat-form-field>
          <button mat-flat-button (click)="discover()" [disabled]="busy()">Discover</button>
        </div>
        <div class="muted small">library = curated public-domain samples (offline) · gutenberg = Project Gutenberg via Gutendex · rss = feeds in pipeline.yaml</div>
        @if (discoverResult()) { <div class="small" style="margin-top:8px">{{ discoverResult() }}</div> }
      </mat-expansion-panel>
      <mat-expansion-panel>
        <mat-expansion-panel-header><mat-panel-title><mat-icon>upload</mat-icon>&nbsp;Add your own story</mat-panel-title></mat-expansion-panel-header>
        <div class="grid cols-2">
          <mat-form-field><mat-label>Title</mat-label><input matInput [(ngModel)]="up.title"></mat-form-field>
          <mat-form-field><mat-label>Author</mat-label><input matInput [(ngModel)]="up.author"></mat-form-field>
        </div>
        <mat-form-field class="full"><mat-label>Story text</mat-label><textarea matInput rows="8" [(ngModel)]="up.text"></textarea></mat-form-field>
        <div class="row">
          <mat-form-field class="dense"><mat-label>Rights claim</mat-label>
            <mat-select [(ngModel)]="up.license_type">@for (l of licenseNames(); track l) { <mat-option [value]="l">{{ l }}</mat-option> }</mat-select>
          </mat-form-field>
          <button mat-flat-button (click)="upload()" [disabled]="busy() || !up.title || up.text.length < 50">Add to library</button>
        </div>
      </mat-expansion-panel>
    </mat-accordion>

    <div class="row" style="margin:16px 0 10px">
      @for (f of filters; track f.value) {
        <button mat-stroked-button [class.active-filter]="filter() === f.value" (click)="filter.set(f.value); load()">{{ f.label }}</button>
      }
      <span class="spacer"></span>
      <mat-form-field class="dense" subscriptSizing="dynamic"><mat-label>Filter</mat-label><input matInput [(ngModel)]="search" (keyup.enter)="load()"></mat-form-field>
    </div>

    <div class="lib-layout">
      <div class="lib-list">
        @for (s of stories(); track s.id) {
          <div class="card story-card" [class.selected]="selected()?.id === s.id" (click)="select(s)">
            <div class="row"><b>{{ s.title }}</b><span class="spacer"></span><app-status [value]="s.rights_status" /></div>
            <div class="muted small">{{ s.author || 'Unknown author' }} · {{ s.word_count }} words · ~{{ s.estimated_minutes }} min · score {{ s.score }}</div>
            <div class="small" style="margin-top:6px">{{ s.synopsis }}</div>
          </div>
        } @empty { <div class="card empty">No stories yet. Open “Discover stories” and run the library connector.</div> }
      </div>

      <div class="lib-detail">
        @if (selected(); as s) {
          <div class="card">
            <div class="row"><h2 style="margin:0">{{ s.title }}</h2><span class="spacer"></span><app-status [value]="s.rights_status" /></div>
            <div class="muted" style="margin:4px 0 14px">{{ s.author }}</div>

            <h3>Provenance</h3>
            <div class="kv" style="margin-bottom:14px">
              <span>Source</span><span>@if (s.source_url) { <a [href]="s.source_url" target="_blank" rel="noopener">{{ s.source_url }}</a> } @else { — }</span>
              <span>Connector</span><span>{{ s.connector }} · {{ s.category }}</span>
              <span>Retrieved</span><span>{{ s.retrieved_at | date:'medium' }}</span>
              <span>Content hash</span><span class="mono">{{ s.content_hash }}</span>
              <span>Claimed license</span><span>{{ s.suggested_license || 'none' }}</span>
              <span>Evidence</span><span>@if (s.license_evidence_url) { <a [href]="s.license_evidence_url" target="_blank" rel="noopener">{{ s.license_evidence_url }}</a> } @else { — }</span>
              <span>Notes</span><span>{{ s.license_notes || '—' }}</span>
              @if (s.rights_decided_by) { <span>Decision</span><span>{{ s.license_type }} by {{ s.rights_decided_by }}, {{ s.rights_decided_at | date:'short' }}</span> }
            </div>

            <h3>Ranking</h3>
            <div class="grid cols-4" style="margin-bottom:14px">
              @for (kv of breakdown(); track kv[0]) {
                <div><div class="muted small">{{ kv[0].replace('_', ' ') }}</div><b>{{ kv[1] }}</b></div>
              }
            </div>

            <h3>Rights decision</h3>
            <div class="grid cols-2">
              <mat-form-field class="dense"><mat-label>Status</mat-label>
                <mat-select [(ngModel)]="rights.status">
                  @for (st of ['approved', 'review_required', 'pending', 'rejected']; track st) { <mat-option [value]="st">{{ st }}</mat-option> }
                </mat-select></mat-form-field>
              <mat-form-field class="dense"><mat-label>License</mat-label>
                <mat-select [(ngModel)]="rights.license_type" (selectionChange)="applyPreset()">
                  @for (l of licenseNames(); track l) { <mat-option [value]="l">{{ l }}</mat-option> }
                </mat-select></mat-form-field>
            </div>
            <mat-form-field class="full dense"><mat-label>Allowed uses</mat-label>
              <mat-select multiple [(ngModel)]="rights.allowed_uses">@for (u of allUses; track u) { <mat-option [value]="u">{{ u }}</mat-option> }</mat-select>
            </mat-form-field>
            <mat-form-field class="full dense"><mat-label>Evidence URL</mat-label><input matInput [(ngModel)]="rights.evidence_url"></mat-form-field>
            <mat-form-field class="full dense"><mat-label>Attribution text</mat-label><input matInput [(ngModel)]="rights.attribution"></mat-form-field>
            <mat-form-field class="full dense"><mat-label>Notes (what you checked)</mat-label><textarea matInput rows="2" [(ngModel)]="rights.notes"></textarea></mat-form-field>
            <div class="row">
              <button mat-flat-button (click)="saveRights()" [disabled]="busy()">Save decision</button>
              @if (s.rights_status === 'approved') {
                <button mat-flat-button color="primary" (click)="createProject(s)"><mat-icon>movie</mat-icon> Create project</button>
              }
            </div>

            <h3 style="margin-top:18px">Text</h3>
            <pre class="story-text">{{ s.text }}</pre>
          </div>
        } @else { <div class="card empty">Select a story to review its provenance and rights.</div> }
      </div>
    </div>
  `,
  styles: [`
    .lib-layout { display: grid; grid-template-columns: minmax(280px, 1fr) minmax(320px, 1.3fr); gap: 14px; align-items: start; }
    @media (max-width: 1000px) { .lib-layout { grid-template-columns: 1fr; } }
    .lib-list { display: flex; flex-direction: column; gap: 10px; }
    .story-card { cursor: pointer; transition: border-color .15s; }
    .story-card:hover { border-color: var(--accent); }
    .story-card.selected { border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent); }
    .lib-detail { position: sticky; top: 12px; }
    .story-text { max-height: 300px; overflow: auto; font-family: Georgia, serif; font-size: 13px; line-height: 1.55; }
    .active-filter { background: var(--progress-bg) !important; color: var(--accent) !important; }
  `],
})
export class LibraryPage implements OnInit {
  private api = inject(Api);
  private router = inject(Router);
  stories = signal<Story[]>([]);
  selected = signal<Story | null>(null);
  connectors = signal<string[]>(['library']);
  presets = signal<Record<string, string[]>>({});
  licenseNames = computed(() => Object.keys(this.presets()));
  breakdown = computed(() => Object.entries(this.selected()?.score_breakdown ?? {}));
  busy = signal(false);
  filter = signal('');
  discoverResult = signal('');
  filters = [{ label: 'All', value: '' }, { label: 'Needs review', value: 'review_required' },
             { label: 'Pending', value: 'pending' }, { label: 'Approved', value: 'approved' }, { label: 'Rejected', value: 'rejected' }];
  allUses = ALL_USES;
  connector = 'library';
  query = '';
  limit = 10;
  search = '';
  up = { title: '', author: '', text: '', license_type: 'user_owned' };
  rights: { status: string; license_type: string; allowed_uses: string[]; evidence_url: string; notes: string; attribution: string } =
    { status: 'approved', license_type: '', allowed_uses: [], evidence_url: '', notes: '', attribution: '' };

  async ngOnInit() {
    const c = await this.api.connectors();
    this.connectors.set(c.connectors);
    this.presets.set(c.license_presets);
    await this.load();
  }

  async load() { this.stories.set(await this.api.stories(this.filter() || undefined, this.search || undefined)); }

  async select(s: Story) {
    const full = await this.api.story(s.id);
    this.selected.set(full);
    const lic = full.rights_status === 'approved' ? full.license_type : (full.suggested_license ?? '');
    this.rights = {
      status: 'approved', license_type: lic,  // the form proposes approval; saving is the explicit decision
      allowed_uses: full.allowed_uses?.length ? [...full.allowed_uses] : [...(this.presets()[lic] ?? [])],
      evidence_url: full.license_evidence_url ?? '', notes: full.license_notes ?? '', attribution: full.attribution ?? '',
    };
  }

  applyPreset() { this.rights.allowed_uses = [...(this.presets()[this.rights.license_type] ?? [])]; }

  async discover() {
    this.busy.set(true);
    try {
      const res = await this.api.discover({ connector: this.connector, query: this.query, limit: this.limit });
      const count = (st: string) => res.filter(r => r.status === st).length;
      this.discoverResult.set(`${res.length} found · ${count('created')} new · ${count('duplicate') + count('near_duplicate')} duplicates · ${count('error')} errors`);
      await this.load();
    } finally { this.busy.set(false); }
  }

  async upload() {
    this.busy.set(true);
    try {
      const r = await this.api.upload(this.up);
      this.api.notify(r.status === 'created' ? 'Story added' : `Not added: ${r.status}`);
      this.up = { title: '', author: '', text: '', license_type: 'user_owned' };
      await this.load();
      await this.select(r.story);
    } finally { this.busy.set(false); }
  }

  async saveRights() {
    const s = this.selected();
    if (!s) return;
    this.busy.set(true);
    try {
      const updated = await this.api.setRights(s.id, { ...this.rights, evidence_url: this.rights.evidence_url || null,
        attribution: this.rights.attribution || null, notes: this.rights.notes || null });
      this.selected.set(updated);
      this.api.notify(`Rights: ${updated.rights_status}`);
      await this.load();
    } finally { this.busy.set(false); }
  }

  async createProject(s: Story) {
    const p = await this.api.createProject(s.id);
    this.router.navigate(['/projects', p.id]);
  }
}
