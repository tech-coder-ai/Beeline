import { DatePipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatSelectModule } from '@angular/material/select';
import { Router, RouterLink } from '@angular/router';
import { Api } from '../../core/api.service';
import { ProjectSummary, Story } from '../../core/models';
import { StatusChip } from '../../shared/status-chip';

@Component({
  selector: 'app-projects',
  imports: [FormsModule, RouterLink, MatButtonModule, MatIconModule, MatFormFieldModule, MatSelectModule, StatusChip, DatePipe],
  template: `
    <div class="page-head">
      <div><h1>Projects</h1><div class="sub">One project = one story going from script to published video.</div></div>
      <div class="row">
        <mat-form-field class="dense" subscriptSizing="dynamic" style="min-width:260px"><mat-label>Approved story</mat-label>
          <mat-select [(ngModel)]="sourceId">
            @for (s of approved(); track s.id) { <mat-option [value]="s.id">{{ s.title }}</mat-option> }
          </mat-select>
        </mat-form-field>
        <mat-form-field class="dense" subscriptSizing="dynamic" style="min-width:220px"><mat-label>Style</mat-label>
          <mat-select [(ngModel)]="style">
            <mat-option value="illustrated_narration">Illustrated narration</mat-option>
            <mat-option value="hybrid_animation">Hybrid animation (AI motion)</mat-option>
          </mat-select>
        </mat-form-field>
        <button mat-flat-button (click)="create()" [disabled]="!sourceId"><mat-icon>add</mat-icon> New project</button>
      </div>
    </div>
    @if (!approved().length) {
      <div class="banner attention"><mat-icon>info</mat-icon><div>No approved stories yet. Approve one in the <a routerLink="/library">story library</a> first. That is the rights gate.</div></div>
    }
    <div class="card table-wrap">
      <table class="data">
        <thead><tr><th>Project</th><th>Status</th><th>Waiting for</th><th>Last job</th><th>Updated</th></tr></thead>
        <tbody>
          @for (p of projects(); track p.id) {
            <tr class="clickable" (click)="open(p.id)">
              <td><b>{{ p.name }}</b><div class="muted small">{{ p.source_title }} · {{ p.languages.join(', ') }} · {{ p.production_style.replace('_', ' ') }}</div></td>
              <td><app-status [value]="p.status" /></td>
              <td>@if (p.pending_checkpoint) { <span class="chip tone-warn">{{ p.pending_checkpoint.replaceAll('_', ' ') }}</span> }</td>
              <td>@if (p.last_job; as j) { {{ j.stage }} <app-status [value]="j.status" /> }</td>
              <td class="muted small">{{ p.updated_at | date:'short' }}</td>
            </tr>
          } @empty { <tr><td colspan="5" class="empty">No projects yet.</td></tr> }
        </tbody>
      </table>
    </div>
  `,
})
export class ProjectsPage implements OnInit {
  private api = inject(Api);
  private router = inject(Router);
  projects = signal<ProjectSummary[]>([]);
  approved = signal<Story[]>([]);
  sourceId = '';
  style = 'illustrated_narration';

  async ngOnInit() {
    const [p, s] = await Promise.all([this.api.projects(), this.api.stories('approved')]);
    this.projects.set(p);
    this.approved.set(s);
  }
  open(id: string) { this.router.navigate(['/projects', id]); }
  async create() {
    const p = await this.api.createProject(this.sourceId, undefined, this.style);
    this.open(p.id);
  }
}
