import { HttpClient, HttpErrorResponse, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { MatSnackBar } from '@angular/material/snack-bar';
import { firstValueFrom, Observable } from 'rxjs';
import { Health, Job, Overview, ProjectDetail, ProjectSummary, Story } from './models';

/** Thin typed client. All business rules live in the backend; errors surface as a snackbar with the API's detail. */
@Injectable({ providedIn: 'root' })
export class Api {
  private http = inject(HttpClient);
  private snack = inject(MatSnackBar);

  private async call<T>(obs: Observable<T>, quiet = false): Promise<T> {
    try {
      return await firstValueFrom(obs);
    } catch (e) {
      if (!quiet) {
        const err = e as HttpErrorResponse;
        const detail = typeof err.error?.detail === 'string' ? err.error.detail
          : err.error?.detail ? JSON.stringify(err.error.detail) : err.message;
        this.snack.open(detail, 'Dismiss', { duration: 8000 });
      }
      throw e;
    }
  }

  notify(message: string) { this.snack.open(message, undefined, { duration: 3000 }); }

  // system
  overview(quiet = false) { return this.call(this.http.get<Overview>('/api/overview'), quiet); }
  health() { return this.call(this.http.get<Health>('/api/health')); }
  settings() { return this.call(this.http.get<Record<string, unknown>>('/api/settings')); }

  // stories
  stories(rights_status?: string, q?: string) {
    let params = new HttpParams();
    if (rights_status) params = params.set('rights_status', rights_status);
    if (q) params = params.set('q', q);
    return this.call(this.http.get<Story[]>('/api/stories', { params }));
  }
  story(id: string) { return this.call(this.http.get<Story>(`/api/stories/${id}`)); }
  connectors() { return this.call(this.http.get<{ connectors: string[]; license_presets: Record<string, string[]> }>('/api/stories/connectors')); }
  discover(body: { connector: string; query: string; limit: number }) {
    return this.call(this.http.post<{ status: string; detail: string; story: Story | null }[]>('/api/stories/discover', body));
  }
  upload(body: Record<string, unknown>) { return this.call(this.http.post<{ status: string; story: Story }>('/api/stories/upload', body)); }
  setRights(id: string, body: Record<string, unknown>) { return this.call(this.http.post<Story>(`/api/stories/${id}/rights`, body)); }
  approveStory(id: string) { return this.call(this.http.post<Story>(`/api/stories/${id}/approve`, {})); }

  // projects
  projects() { return this.call(this.http.get<ProjectSummary[]>('/api/projects')); }
  project(id: string, quiet = false) { return this.call(this.http.get<ProjectDetail>(`/api/projects/${id}`), quiet); }
  createProject(source_id: string, name?: string, production_style?: string) {
    return this.call(this.http.post<ProjectDetail>('/api/projects', { source_id, name: name || null, production_style: production_style || null }));
  }
  run(id: string) { return this.call(this.http.post<Job>(`/api/projects/${id}/run`, {})); }
  runStage(id: string, stage: string) { return this.call(this.http.post<Job>(`/api/projects/${id}/stages/${stage}`, {})); }
  publish(id: string, body: { visibility: string; languages: string[] }) {
    return this.call(this.http.post<Job>(`/api/projects/${id}/publish`, body));
  }
  approve(id: string, checkpoint: string, note: string) {
    return this.call(this.http.post(`/api/projects/${id}/checkpoints/${checkpoint}/approve`, { note, continue_pipeline: true }));
  }
  reject(id: string, checkpoint: string, note: string) {
    return this.call(this.http.post(`/api/projects/${id}/checkpoints/${checkpoint}/reject`, { note }));
  }
  regenerateScene(id: string, sceneId: string) { return this.call(this.http.post<Job>(`/api/projects/${id}/scenes/${sceneId}/regenerate`, {})); }
  regenerateCharacter(id: string, charId: string) { return this.call(this.http.post<Job>(`/api/projects/${id}/characters/${charId}/regenerate`, {})); }
  editSegment(id: string, lang: string, segmentId: string, text: string) {
    return this.call(this.http.patch(`/api/projects/${id}/localizations/${lang}/segments/${segmentId}`, { text }));
  }
  cancelProject(id: string) { return this.call(this.http.post(`/api/projects/${id}/cancel`, {})); }

  // jobs
  retryJob(id: string) { return this.call(this.http.post<Job>(`/api/jobs/${id}/retry`, {})); }
  cancelJob(id: string) { return this.call(this.http.post<Job>(`/api/jobs/${id}/cancel`, {})); }
}
