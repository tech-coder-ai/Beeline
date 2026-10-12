# Story-to-YouTube Pipeline

> New here? Read the [study guide](docs/study-guide.html) for the reasoning behind every design decision.

A self-hosted production pipeline that takes a story from **discovery** to a **finished, subtitled,
multilingual YouTube video**, with human approval checkpoints and a hard rights gate.

```
Story sources ─► Discovery connectors ─► Rights & provenance review ─► Story library
   ─► [script]      LLM story bible + characters + scene spec   (deterministic checks)   ◆ checkpoint
   ─► [characters]  reference sheets (image model)                                        ◆ checkpoint
   ─► [scenes]      one illustration per scene, conditioned on the sheets
   ─► [animate]     hybrid projects only: key scenes -> AI image-to-video clips (Wan 2.2)
   ─► [audio]       translate per language ─► TTS per segment
   ─► [render]      timeline from measured audio ─► FFmpeg (Ken Burns, subtitles, loudness)
   ─► [qc]          ffprobe / volumedetect / blackdetect / subtitle / metadata / rights checks ◆ final approval
   ─► [publish]     idempotent YouTube upload (private first)
```

Every stage is an independent, replaceable service. The workflow engine only orchestrates. AI is
used for the creative work, and plain code handles validation, retries, files and publishing.

## Run it (5 minutes, no GPU, no API keys)

Requirements: Python 3.11+, Node 20+, and FFmpeg built with `libx264`, `libass` and (for offline English
voices) `libflite`. Ubuntu's `ffmpeg` package has all three.

```bash
cd story-pipeline/backend
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest                         # 26 tests, including full offline renders
.venv/bin/uvicorn app.main:app --port 8000

cd ../frontend && npm ci && npx ng serve  # http://localhost:4200
# or: npx ng build, then the backend serves the UI at http://localhost:8000
```

Then open **Story library → Discover stories → library**, approve a fable, create a project, and press
**Run**. Out of the box the pipeline runs fully offline:

| Capability | Default (offline) | Production provider | Switch with |
|---|---|---|---|
| LLM | `offline`: deterministic scene splitter, template metadata, **no translation** | Ollama / any OpenAI-compatible server | `SPA_LLM_PROVIDER=ollama SPA_LLM_MODEL=llama3.1:8b` |
| Images | `placeholder`: Pillow storyboard cards | ComfyUI workflows | `SPA_IMAGE_PROVIDER=comfyui` |
| Animation (hybrid projects) | `none`: every scene is a still with a camera move (`placeholder` fakes motion with FFmpeg) | Wan 2.2 14B image-to-video in ComfyUI | `SPA_VIDEO_PROVIDER=comfyui` |
| Voices | FFmpeg `flite` (English) | Piper neural TTS | `config/languages.yaml` |
| Publishing | `dry_run`: writes a receipt | YouTube Data API v3 | `SPA_PUBLISH_PROVIDER=youtube` + `scripts/youtube_auth.py` |

Hindi (`hi`) is a configured target language. With no LLM it is **skipped and reported**; it is never
faked. Configure Ollama to get translated Hindi tracks; install Piper voices for Hindi audio. Until then,
the configured `silent` fallback renders it subtitled, and QC flags it.

## Production setup

1. **LLM**: install [Ollama](https://ollama.com), `ollama pull llama3.1:8b`, set `models.llm.provider: ollama`.
   Responses are schema-constrained (`format=<JSON schema>`) *and* validated with Pydantic, with a repair loop.
2. **Images**: run [ComfyUI](https://docs.comfy.org/), export your workflows in API format into
   `comfyui-workflows/` using the `{{prompt}}`/`{{seed}}`/`{{reference_image}}` tokens (see that folder's README),
   and set `models.image.provider: comfyui`.
3. **AI animation (optional)**: create projects with style *Hybrid animation*. Download the Wan 2.2 14B
   image-to-video fp8 files listed in `comfyui-workflows/README.md` (~20 GB VRAM; a 48 GB card runs 720p),
   check ComfyUI's own Wan 2.2 I2V template works, and set `models.video.provider: comfyui`. Only scenes the
   script marks `animate` are animated (capped by `max_animated_scenes`); the rest keep the Ken Burns treatment.
   Set `models.llm.keep_alive: "0"` so Ollama releases VRAM for the video model.
4. **Voices**: `pip install piper-tts`, download voices (e.g. `hi_IN-pratham-medium.onnx` + `.json`) into
   `models/piper/`, and reference them in `config/languages.yaml`.
5. **YouTube**: create an OAuth desktop client, save it as `secrets/client_secret.json`, run
   `pip install -e "backend[youtube]" && python scripts/youtube_auth.py`, and set `publishing.provider: youtube`.
   Uploads default to **private**.

`GET /api/health` (Settings screen) checks every provider and voice against what is actually installed.

## Project layout

```
story-pipeline/
├── config/                 pipeline.yaml, languages.yaml (voice registry), prompts/*.md
├── comfyui-workflows/      versioned image workflows (API format)
├── sample_stories/         public-domain fables (Townsend's Aesop, 1867) with license evidence
├── scripts/                dev.sh, youtube_auth.py
├── backend/app/
│   ├── config.py           typed settings + env overrides + config version hash
│   ├── domain/states.py    the state machine (statuses, stages, checkpoints)
│   ├── workflow/           engine (queue, retries, checkpoints), runner (worker thread), context
│   ├── providers/          llm/ images/ tts/ youtube/  - one interface + adapters each
│   ├── services/           discovery, rights, story, characters, scenes, localization,
│   │                       audio, rendering, quality, publishing, assets
│   ├── persistence/        SQLAlchemy models (12 entities) + session handling
│   ├── api/                FastAPI routers + serializers (the UI contract)
│   └── main.py
├── backend/tests/          states, story checks, rights gate, engine/resume, timeline, e2e
└── frontend/               Angular 20 + Material dashboard ("Story Studio")
```

Each project's files live under `data/projects/<id>/` in the layout from the plan
(`story/`, `assets/characters|scenes/`, `languages/<code>/{audio,subtitles.srt,final.mp4}`, `metadata/`),
and every file is registered in the `assets` table with checksum, provider, model, prompt and seed.

## Key behaviours

- **Approval mode** (default) pauses after the script, the character sheets and the final render. Approving the
  final cut unlocks publishing but does not upload. `pipeline.mode: fully_automated` runs straight through, but
  `publishing.require_approval: true` still forces a human to approve the final render.
- **Rights gate**: discovery never approves rights. A person must record a license, evidence and allowed
  uses. Projects can only be created from approved sources, and rights are re-checked in QC and before upload.
  Licenses without `verbatim` force an LLM-written original adaptation (a verbatim-overlap check blocks close copies).
- **Resumable**: every scene image, voice segment, clip and render is cached by a fingerprint of its inputs.
  A retry or rerun only regenerates what changed (e.g. scene 18 of 30). Interrupted jobs resume after a restart.
- **Targeted regeneration**: redraw one character or scene (new seed), or edit one translated line and re-voice just that segment.
- **Idempotent publishing**: one stable `attempt_id` per upload. After a timeout the publisher first looks
  for a video carrying that id before uploading again.

## API

Interactive docs at `http://localhost:8000/docs`. Main endpoints:

| Endpoint | Purpose |
|---|---|
| `POST /api/stories/discover` · `POST /api/stories/upload` | find / add candidates |
| `POST /api/stories/{id}/rights` · `/approve` | record the rights decision |
| `POST /api/projects` | create a project (approved sources only) |
| `POST /api/projects/{id}/run` | run until the next checkpoint / failure / end |
| `POST /api/projects/{id}/generate-script` · `generate-characters` · `generate-scenes` · `localize` · `render` · `qc` | run one stage |
| `POST /api/projects/{id}/checkpoints/{cp}/approve` · `/reject` | human decisions |
| `POST /api/projects/{id}/scenes/{scene}/regenerate` · `characters/{char}/regenerate` | targeted redo |
| `PATCH /api/projects/{id}/localizations/{lang}/segments/{seg}` | fix one translated line |
| `POST /api/projects/{id}/publish` | upload QC-approved renders |
| `GET /api/jobs/{id}` · `POST /api/jobs/{id}/retry` · `/cancel` | job control |
| `GET /api/overview` · `GET /api/health` · `GET /api/settings` | dashboard, provider checks, config |

## Scope notes

This is the MVP from the implementation plan: illustrated narration plus optional hybrid animation, private
uploads, and English with a Hindi target. The Wan 2.2 workflow template and the real ComfyUI/Ollama/Piper/YouTube
adapters have not been run against the real services in this repo's CI. Not included yet: episode splitting for long
novels, full animated production, background-music generation, multi-user auth, and Alembic migrations (tables are created on startup;
add Alembic before the schema has to evolve under real data). Until then, after pulling a schema change
(e.g. the `scenes.motion_*` columns), delete `data/pipeline.db` or add the columns by hand.
