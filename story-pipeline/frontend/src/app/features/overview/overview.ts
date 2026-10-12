import { DecimalPipe, DatePipe } from '@angular/common';
import { Component, OnDestroy, OnInit, computed, inject, signal } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { RouterLink } from '@angular/router';
import { Api } from '../../core/api.service';
import { Overview } from '../../core/models';
import { StatusChip } from '../../shared/status-chip';

@Component({
  selector: 'app-overview',
  imports: [RouterLink, MatIconModule, MatProgressBarModule, StatusChip, DecimalPipe, DatePipe],
  template: `
    <div class="page-head">
      <div><h1>Overview</h1><div class="sub">What the pipeline is doing right now, and where time goes.</div></div>
    </div>
    @if (data(); as d) {
      <div class="grid cols-4" style="margin-bottom:14px">
        <div class="card stat"><span class="label">Projects</span><span class="value">{{ totalProjects() }}</span></div>
        <div class="card stat"><span class="label">Awaiting approval</span><span class="value">{{ d.awaiting_approval.length }}</span></div>
        <div class="card stat"><span class="label">Published videos</span><span class="value">{{ d.published }}</span></div>
        <div class="card stat"><span class="label">Asset storage</span><span class="value">{{ d.storage_bytes / 1048576 | number:'1.0-0' }} MB</span></div>
      </div>

      <div class="grid cols-2">
        <section class="card">
          <h2>Needs your decision</h2>
          @for (a of d.awaiting_approval; track a.id) {
            <a class="row" style="padding:8px 0; text-decoration:none; color:inherit" [routerLink]="['/projects', a.id]">
              <mat-icon style="color:var(--warn)">pending_actions</mat-icon>
              <span><b>{{ a.name }}</b> <span class="muted">at</span> {{ a.checkpoint.replaceAll('_', ' ') }}</span>
            </a>
          } @empty { <div class="muted">Nothing waiting. </div> }
          <h2 style="margin-top:18px">Running now</h2>
          @for (j of d.active_jobs; track j.id) {
            <div style="padding:6px 0">
              <div class="row"><a [routerLink]="['/projects', j.project_id]">{{ j.stage }}</a><app-status [value]="j.status" /><span class="muted small">{{ j.message }}</span></div>
              <mat-progress-bar mode="determinate" [value]="j.progress * 100" />
            </div>
          } @empty { <div class="muted">No active jobs.</div> }
        </section>

        <section class="card">
          <h2>Stage timings</h2>
          <p class="muted small" style="margin-top:-6px">Measured per successful run. The slowest stage is your bottleneck: optimise or buy hardware for that one.</p>
          <div class="table-wrap"><table class="data">
            <thead><tr><th>Stage</th><th>Runs</th><th>Average</th><th>Slowest</th></tr></thead>
            <tbody>
              @for (t of timings(); track t.stage) {
                <tr><td>{{ t.stage }}</td><td>{{ t.runs }}</td><td>{{ t.avg_seconds | number:'1.0-1' }} s</td><td>{{ t.max_seconds | number:'1.0-1' }} s</td></tr>
              } @empty { <tr><td colspan="4" class="muted">No completed stages yet.</td></tr> }
            </tbody>
          </table></div>
        </section>

        <section class="card">
          <h2>Recent failures</h2>
          @for (j of d.failed_jobs; track j.id) {
            <div style="padding:6px 0; border-bottom:1px solid var(--border)">
              <div class="row"><a [routerLink]="['/projects', j.project_id]">{{ j.stage }}</a><span class="muted small">{{ j.finished_at | date:'short' }}</span></div>
              <div class="small" style="color:var(--bad)">{{ (j.error || '').split('\\n')[0] }}</div>
            </div>
          } @empty { <div class="muted">No failures.</div> }
        </section>

        <section class="card">
          <h2>Library & projects</h2>
          <div class="row" style="margin-bottom:10px">
            @for (kv of rights(); track kv[0]) { <app-status [value]="kv[0]" /> <b>{{ kv[1] }}</b> }
          </div>
          <div class="row">
            @for (kv of statuses(); track kv[0]) { <app-status [value]="kv[0]" /> <b>{{ kv[1] }}</b> }
          </div>
          <div class="row" style="margin-top:14px">
            <a routerLink="/library">Review stories →</a><a routerLink="/projects">Open projects →</a>
          </div>
        </section>
      </div>
    } @else { <mat-progress-bar mode="indeterminate" /> }
  `,
})
export class OverviewPage implements OnInit, OnDestroy {
  private api = inject(Api);
  data = signal<Overview | null>(null);
  private timer?: ReturnType<typeof setInterval>;

  totalProjects = computed(() => Object.values(this.data()?.projects_by_status ?? {}).reduce((a, b) => a + b, 0));
  timings = computed(() => Object.entries(this.data()?.stage_timings ?? {}).map(([stage, t]) => ({ stage, ...t })));
  rights = computed(() => Object.entries(this.data()?.stories_by_rights ?? {}));
  statuses = computed(() => Object.entries(this.data()?.projects_by_status ?? {}));

  ngOnInit() {
    this.load();
    this.timer = setInterval(() => this.load(true), 4000);
  }
  ngOnDestroy() { clearInterval(this.timer); }
  async load(quiet = false) { this.data.set(await this.api.overview(quiet)); }
}
