// Mirrors backend/app/api/serializers.py - the UI contract.
export type RightsStatus = 'pending' | 'approved' | 'rejected' | 'review_required';
export type JobStatus = 'QUEUED' | 'RUNNING' | 'SUCCEEDED' | 'FAILED' | 'RETRY_PENDING' | 'CANCELLED';

export interface Story {
  id: string; connector: string; title: string; author: string | null; source_url: string | null;
  published: string | null; language: string; category: string; synopsis: string | null; word_count: number;
  content_hash: string; license_type: string; suggested_license: string | null; license_evidence_url: string | null;
  license_notes: string | null; rights_status: RightsStatus; allowed_uses: string[]; attribution: string | null;
  rights_decided_by: string | null; rights_decided_at: string | null; retrieved_at: string; score: number;
  score_breakdown: Record<string, number>; estimated_minutes: number; text?: string;
}

export interface Job {
  id: string; project_id: string; stage: string; status: JobStatus; attempts: number; max_attempts: number;
  progress: number; message: string | null; error: string | null; output: Record<string, unknown>;
  continue_pipeline: boolean; cancel_requested: boolean; config_version: string; created_at: string;
  started_at: string | null; finished_at: string | null; duration_seconds: number | null; not_before: string | null;
}

export interface ProjectSummary {
  id: string; name: string; status: string; pending_checkpoint: string | null; production_style: string;
  source_id: string; source_title: string; languages: string[]; config_version: string; created_at: string;
  updated_at: string; last_job: Job | null;
}

export interface StageView {
  stage: string; label: string; requires: string; produces: string; checkpoint: string | null;
  can_run: boolean; is_next: boolean; latest_job: Job | null;
}

export interface Issue { severity: 'error' | 'warning'; code: string; message: string; scene_id: string | null; }
export interface ScriptLine { speaker: string; text: string; }
export interface SceneSpec {
  scene_id: string; sequence: number; title: string; duration_seconds: number; location_id: string;
  characters: string[]; lines: ScriptLine[]; visual_prompt: string;
  camera: { shot_type: string; movement: string }; mood: string; music_cue: string; continuity_requirements: string[];
  animate: boolean; motion_prompt: string;
}
export interface CharacterProfile {
  character_id: string; name: string; role: string; age_range: string; personality: string[]; description: string;
  appearance: { species: string; build: string; hair: string; clothing_style: string; distinctive_features: string[]; palette: string[] };
  voice_profile: { voice_id: string | null; speaking_style: string };
}
export interface QcCheck { name: string; status: 'pass' | 'warn' | 'fail'; detail: string; }

export interface ProjectDetail extends ProjectSummary {
  stages: StageView[];
  jobs: Job[];
  source: Story;
  story: null | {
    id: string; version: number; generated_by: string; approved: boolean; created_at: string; issues: Issue[];
    bible: { title: string; synopsis: string; genre: string; tone: string; audience: string; moral: string;
             preserved_facts: string[]; permitted_changes: string[]; locations: { location_id: string; name: string }[] };
    script: { title: string; hook: string; ending: string; scenes: SceneSpec[] };
  };
  characters: { id: string; character_id: string; name: string; profile: CharacterProfile; seed: number;
                approved: boolean; reference_url: string | null }[];
  scenes: { id: string; scene_id: string; sequence: number; spec: SceneSpec; seed: number; status: string;
            error: string | null; image_url: string | null; motion_url: string | null;
            motion_status: string | null; motion_error: string | null }[];
  localizations: { language: string; status: string; generated_by: string; note: string | null;
                   segments: { segment_id: string; scene_id: string; speaker: string; text: string }[];
                   audio: { segment_id: string; scene_id: string; speaker: string; text: string; voice_id: string;
                            tts_provider: string; duration: number; status: string; note: string | null;
                            audio_url: string | null }[] }[];
  renders: { id: string; language: string; status: string; duration: number | null; video_url: string | null;
             subtitles_url: string | null; thumbnail_url: string | null; render_seconds: number;
             metadata: { title?: string; description?: string; tags?: string[]; generated_by?: string };
             qc: { checks?: QcCheck[]; passed?: boolean }; qc_passed: boolean | null; updated_at: string;
             scene_times: { scene_id: string; start: number; end: number }[] }[];
  publications: { id: string; language: string; attempt_id: string; provider: string; video_id: string | null;
                  url: string | null; visibility: string; status: string; processing_status: string | null;
                  retries: number; last_error: string | null; confirmed_at: string | null; title: string | null }[];
  approvals: { id: string; checkpoint: string; decision: string; decided_by: string; note: string | null; created_at: string }[];
  can_publish: boolean;
}

export interface Overview {
  projects_by_status: Record<string, number>;
  awaiting_approval: { id: string; name: string; checkpoint: string }[];
  stories_by_rights: Record<string, number>;
  active_jobs: Job[]; failed_jobs: Job[]; recent_jobs: Job[]; published: number;
  stage_timings: Record<string, { runs: number; avg_seconds: number; max_seconds: number }>;
  storage_bytes: number;
}

export interface HealthItem { ok: boolean; detail: string; provider?: string; }
export interface Health {
  config_version: string; mode: string; llm: HealthItem; image: HealthItem; video: HealthItem; ffmpeg: HealthItem; publisher: HealthItem;
  voices: (HealthItem & { language: string; voice_id: string; provider: string; voice: string })[];
}

export const CHECKPOINT_HELP: Record<string, string> = {
  story_adaptation: 'Review the story bible, characters and scene breakdown before any art is generated.',
  character_generation: 'Approve the character reference sheets. Every scene is drawn from these, so fix looks now.',
  scene_generation: 'Approve the scene illustrations before voices and rendering.',
  final_render: 'Watch the final video and read the QC report. Approving allows publishing; it does not upload.',
};
