import { Component, computed, input } from '@angular/core';

const TONE: Record<string, string> = {
  approved: 'ok', SUCCEEDED: 'ok', UPLOADED: 'ok', QC_APPROVED: 'ok', ready: 'ok', rendered: 'ok', uploaded: 'ok',
  pass: 'ok', processed: 'ok', ok: 'ok', generated: 'ok',
  pending: 'muted', QUEUED: 'info', CREATED: 'muted', skipped: 'muted', CANCELLED: 'muted',
  review_required: 'warn', RETRY_PENDING: 'warn', warn: 'warn', fallback: 'warn', uploading: 'info',
  rejected: 'bad', FAILED: 'bad', failed: 'bad', fail: 'bad', RUNNING: 'info',
};

/** One consistent colour language for every status string the backend produces. */
@Component({
  selector: 'app-status',
  template: `<span class="chip" [class]="'chip tone-' + tone()">{{ label() }}</span>`,
})
export class StatusChip {
  value = input.required<string | null | undefined>();
  tone = computed(() => TONE[this.value() ?? ''] ?? (this.value()?.endsWith('_READY') || this.value() === 'QC_PASSED' || this.value() === 'RENDERED' ? 'progress' : 'muted'));
  label = computed(() => (this.value() ?? '-').replace(/_/g, ' ').toLowerCase());
}
