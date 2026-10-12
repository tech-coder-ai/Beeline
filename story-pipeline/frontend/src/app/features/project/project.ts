import { DatePipe, DecimalPipe, JsonPipe } from '@angular/common';
import { Component, OnDestroy, computed, effect, inject, input, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatSelectModule } from '@angular/material/select';
import { MatTabsModule } from '@angular/material/tabs';
import { MatTooltipModule } from '@angular/material/tooltip';
import { RouterLink } from '@angular/router';
import { Api } from '../../core/api.service';
import { CHECKPOINT_HELP, Job, ProjectDetail, StageView } from '../../core/models';
import { StatusChip } from '../../shared/status-chip';

@Component({
  selector: 'app-project',
  imports: [FormsModule, RouterLink, MatButtonModule, MatIconModule, MatTabsModule, MatProgressBarModule,
            MatFormFieldModule, MatInputModule, MatSelectModule, MatCheckboxModule, MatTooltipModule,
            StatusChip, DatePipe, DecimalPipe, JsonPipe],
  templateUrl: './project.html',
  styleUrl: './project.scss',
})
export class ProjectPage implements OnDestroy {
  private api = inject(Api);
  id = input.required<string>();
  p = signal<ProjectDetail | null>(null);
  note = '';
  visibility = 'private';
  publishLangs: string[] = [];
  edits: Record<string, string> = {};
  help = CHECKPOINT_HELP;
  private timer?: ReturnType<typeof setTimeout>;

  activeJob = computed(() => this.p()?.jobs.find(j => ['QUEUED', 'RUNNING', 'RETRY_PENDING'].includes(j.status)) ?? null);
  nextStage = computed(() => this.p()?.stages.find(s => s.is_next) ?? null);
  names = computed(() => Object.fromEntries((this.p()?.characters ?? []).map(c => [c.character_id, c.name])));
  publishable = computed(() => (this.p()?.renders ?? []).filter(r => r.qc_passed && r.status === 'rendered'));

  constructor() {
    effect(() => { this.id(); this.load(); });
  }
  ngOnDestroy() { clearTimeout(this.timer); }

  async load(quiet = false) {
    clearTimeout(this.timer);
    try {
      const d = await this.api.project(this.id(), quiet);
      this.p.set(d);
      if (!this.publishLangs.length) this.publishLangs = d.renders.filter(r => r.qc_passed).map(r => r.language);
    } finally {
      // poll fast while work is happening, slowly otherwise
      this.timer = setTimeout(() => this.load(true), this.activeJob() ? 1500 : 8000);
    }
  }

  stageState(s: StageView): string {
    const j = s.latest_job;
    if (j && ['QUEUED', 'RUNNING', 'RETRY_PENDING', 'FAILED'].includes(j.status)) return j.status;
    if (this.p()?.pending_checkpoint && s.checkpoint === this.p()?.pending_checkpoint) return 'awaiting approval';
    if (s.is_next) return 'next';
    if (j?.status === 'SUCCEEDED') return 'done';
    return s.can_run ? 'ready' : 'locked';
  }

  speaker(id: string) { return id === 'narrator' ? 'Narrator' : (this.names()[id] ?? id); }
  firstLine(text: string | null) { return (text ?? '').split('\n')[0]; }
  outputKeys(j: Job) { return Object.keys(j.output ?? {}).length > 0; }

  private async act(fn: () => Promise<unknown>, msg?: string) {
    await fn();
    if (msg) this.api.notify(msg);
    this.note = '';
    await this.load();
  }
  run() { return this.act(() => this.api.run(this.id()), 'Pipeline started'); }
  runStage(stage: string) { return this.act(() => this.api.runStage(this.id(), stage), `${stage} queued`); }
  approve(cp: string) { return this.act(() => this.api.approve(this.id(), cp, this.note), 'Approved'); }
  reject(cp: string) { return this.act(() => this.api.reject(this.id(), cp, this.note), 'Sent back for rework'); }
  retry(j: Job) { return this.act(() => this.api.retryJob(j.id), 'Retry queued'); }
  cancelJob(j: Job) { return this.act(() => this.api.cancelJob(j.id), 'Cancellation requested'); }
  regenScene(sceneId: string) { return this.act(() => this.api.regenerateScene(this.id(), sceneId), `Redrawing ${sceneId}`); }
  regenChar(charId: string) { return this.act(() => this.api.regenerateCharacter(this.id(), charId), `Redrawing ${charId}`); }
  publish() {
    return this.act(() => this.api.publish(this.id(), { visibility: this.visibility, languages: this.publishLangs }), 'Publishing queued');
  }
  async saveSegment(lang: string, segmentId: string) {
    const key = `${lang}/${segmentId}`;
    await this.act(() => this.api.editSegment(this.id(), lang, segmentId, this.edits[key]),
                   'Saved. Run "Localization, voices & subtitles" to re-voice this line.');
    delete this.edits[key];
  }
  cancelProject() {
    if (confirm('Cancel this project? Running work stops at the next item.')) {
      return this.act(() => this.api.cancelProject(this.id()), 'Project cancelled');
    }
    return Promise.resolve();
  }
}
