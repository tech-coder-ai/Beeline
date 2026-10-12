"""What a stage handler receives: settings, providers, storage, progress and cancellation."""
from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from typing import Any, TypeVar

from sqlalchemy.orm import Session

from app.config import Settings
from app.persistence.models import WorkflowJob
from app.services.assets import AssetStore

T = TypeVar("T")


class Cancelled(Exception):
    pass


class StageFailed(Exception):
    """A deterministic failure (validation, missing input) - retrying won't help."""


@dataclass
class StageContext:
    settings: Settings
    project_id: str
    job_id: str
    options: dict[str, Any]
    session_factory: Callable[[], AbstractContextManager[Session]]
    assets: AssetStore
    warnings: list[str] = field(default_factory=list)

    def db(self) -> AbstractContextManager[Session]:
        """Short transactions: commit each item as it finishes so progress survives a crash."""
        return self.session_factory()

    def progress(self, fraction: float, message: str) -> None:
        with self.db() as s:
            job = s.get(WorkflowJob, self.job_id)
            if job:
                job.progress = max(0.0, min(1.0, fraction))
                job.message = message[:500]

    def check_cancelled(self) -> None:
        with self.db() as s:
            job = s.get(WorkflowJob, self.job_id)
            if job and job.cancel_requested:
                raise Cancelled()

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    @staticmethod
    def run_async(coro: Coroutine[Any, Any, T]) -> T:
        return asyncio.run(coro)
