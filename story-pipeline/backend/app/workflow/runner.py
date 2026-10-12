"""Background job runner: a single worker thread that polls the jobs table.

One job at a time is deliberate - on a single-GPU workstation, running two
heavy stages concurrently mostly produces out-of-memory errors. Parallelism
happens *inside* a stage where it is safe (e.g. max_parallel_scenes).
"""
from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime

from sqlalchemy import or_, select

from app.config import Settings
from app.domain.states import JobStatus
from app.persistence.db import session_scope
from app.persistence.models import WorkflowJob
from app.workflow.engine import recover_interrupted, run_job

log = logging.getLogger("runner")


def next_runnable_job_id() -> str | None:
    now = datetime.now(UTC)
    with session_scope() as db:
        jobs = db.scalars(
            select(WorkflowJob)
            .where(WorkflowJob.status.in_([JobStatus.QUEUED.value, JobStatus.RETRY_PENDING.value]))
            .where(or_(WorkflowJob.not_before.is_(None), WorkflowJob.not_before <= now))
            .order_by(WorkflowJob.created_at)
        ).all()
        # SQLite returns naive datetimes; compare defensively.
        for j in jobs:
            nb = j.not_before
            if nb is not None and nb.tzinfo is None:
                nb = nb.replace(tzinfo=UTC)
            if nb is None or nb <= now:
                return j.id
    return None


def drain(settings: Settings, max_jobs: int = 100) -> int:
    """Run queued jobs synchronously until none are runnable (used by tests and the CLI)."""
    n = 0
    while n < max_jobs:
        job_id = next_runnable_job_id()
        if job_id is None:
            return n
        run_job(job_id, settings)
        n += 1
    return n


class JobRunner:
    def __init__(self, settings: Settings, poll_seconds: float = 1.0):
        self.settings = settings
        self.poll_seconds = poll_seconds
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        with session_scope() as db:
            n = recover_interrupted(db)
        if n:
            log.info("re-queued %d interrupted job(s)", n)
        self._thread = threading.Thread(target=self._loop, name="job-runner", daemon=True)
        self._thread.start()

    def wake(self) -> None:
        self._wake.set()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread:
            self._thread.join(timeout=10)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                job_id = next_runnable_job_id()
                if job_id:
                    run_job(job_id, self.settings)
                    continue
            except Exception:  # noqa: BLE001 - the runner must never die
                log.exception("runner loop error")
            self._wake.wait(self.poll_seconds)
            self._wake.clear()
