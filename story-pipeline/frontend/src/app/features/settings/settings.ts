import { JsonPipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { Api } from '../../core/api.service';
import { Health, HealthItem } from '../../core/models';

@Component({
  selector: 'app-settings',
  imports: [MatIconModule, MatButtonModule, MatProgressBarModule, JsonPipe],
  template: `
    <div class="page-head">
      <div><h1>Settings & health</h1><div class="sub">Configuration lives in <span class="mono">config/pipeline.yaml</span> and <span class="mono">config/languages.yaml</span>. Edit there (or use SPA_* env vars) and restart.</div></div>
      <button mat-stroked-button (click)="load()"><mat-icon>refresh</mat-icon> Re-check</button>
    </div>
    @if (health(); as h) {
      <div class="grid cols-3" style="margin-bottom:14px">
        @for (item of items(h); track item.name) {
          <div class="card">
            <div class="row"><mat-icon [style.color]="item.v.ok ? 'var(--ok)' : 'var(--bad)'">{{ item.v.ok ? 'check_circle' : 'error' }}</mat-icon><b>{{ item.name }}</b></div>
            <div class="mono" style="margin:6px 0">{{ item.v.provider || '' }}</div>
            <div class="small muted">{{ item.v.detail }}</div>
          </div>
        }
      </div>
      <div class="card table-wrap" style="margin-bottom:14px">
        <h2>Voice registry</h2>
        <table class="data">
          <thead><tr><th>Language</th><th>Voice id</th><th>Engine</th><th>Model</th><th>Status</th></tr></thead>
          <tbody>
            @for (v of h.voices; track v.voice_id) {
              <tr><td>{{ v.language }}</td><td class="mono">{{ v.voice_id }}</td><td>{{ v.provider }}</td><td class="mono">{{ v.voice }}</td>
                <td [style.color]="v.ok ? 'var(--ok)' : 'var(--warn)'">{{ v.detail }}</td></tr>
            }
          </tbody>
        </table>
        <p class="small muted">Voices that are unavailable fall back to the language's fallback voice (silent by default) and QC flags them.</p>
      </div>
      <div class="card"><h2>Effective configuration <span class="muted small mono">v{{ h.config_version }}</span></h2><pre>{{ config() | json }}</pre></div>
    } @else { <mat-progress-bar mode="indeterminate" /> }
  `,
})
export class SettingsPage implements OnInit {
  private api = inject(Api);
  health = signal<Health | null>(null);
  config = signal<Record<string, unknown> | null>(null);

  ngOnInit() { this.load(); }
  async load() {
    this.health.set(null);
    const [h, c] = await Promise.all([this.api.health(), this.api.settings()]);
    this.config.set(c);
    this.health.set(h);
  }
  items(h: Health): { name: string; v: HealthItem }[] {
    return [{ name: 'Language model', v: h.llm }, { name: 'Image generation', v: h.image },
            { name: 'Image-to-video', v: h.video },
            { name: 'FFmpeg', v: h.ffmpeg }, { name: 'Publisher', v: h.publisher }];
  }
}
