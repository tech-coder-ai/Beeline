# Story Studio (Angular dashboard)

Angular 20 standalone components + signals + Angular Material. No business logic lives here: every
action calls the FastAPI backend, which owns workflow state, approvals and the rights gate.

```bash
npm ci
npx ng serve          # http://localhost:4200, proxies /api -> http://localhost:8000 (proxy.conf.json)
npx ng build          # dist/story-studio/browser - the backend serves this automatically if present
```

| Path | Screen |
|---|---|
| `src/app/core/api.service.ts` | typed API client, error snackbars |
| `src/app/core/models.ts` | the UI contract (mirrors `backend/app/api/serializers.py`) |
| `features/overview` | active jobs, approvals waiting, stage timings |
| `features/library` | discovery, upload, provenance, rights decisions |
| `features/projects` | project list / creation from approved stories |
| `features/project` | pipeline, checkpoints, story, characters, scenes, voices, video + QC, publishing, jobs |
| `features/settings` | provider health, voice registry, effective config |
