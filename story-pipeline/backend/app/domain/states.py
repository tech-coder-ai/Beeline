"""The production state machine.

A project only ever moves forward through these states by running a stage
(or by a human approving a checkpoint). Keeping the transitions in one table
means the API, the workflow engine and the UI all agree on what "next" means.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ProjectStatus(str, Enum):
    CREATED = "CREATED"
    SOURCE_APPROVED = "SOURCE_APPROVED"
    SCRIPT_READY = "SCRIPT_READY"
    CHARACTERS_READY = "CHARACTERS_READY"
    SCENES_READY = "SCENES_READY"
    AUDIO_READY = "AUDIO_READY"
    RENDERED = "RENDERED"
    QC_PASSED = "QC_PASSED"
    QC_APPROVED = "QC_APPROVED"
    UPLOADED = "UPLOADED"
    CANCELLED = "CANCELLED"


ORDER = [s for s in ProjectStatus if s is not ProjectStatus.CANCELLED]


def rank(status: ProjectStatus | str) -> int:
    return ORDER.index(ProjectStatus(status))


class Stage(str, Enum):
    SCRIPT = "script"
    CHARACTERS = "characters"
    SCENES = "scenes"
    AUDIO = "audio"
    RENDER = "render"
    QC = "qc"
    PUBLISH = "publish"


class JobStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    RETRY_PENDING = "RETRY_PENDING"
    CANCELLED = "CANCELLED"


ACTIVE_JOB_STATUSES = {JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.RETRY_PENDING}


@dataclass(frozen=True)
class StageSpec:
    stage: Stage
    requires: ProjectStatus      # minimum project status to start
    produces: ProjectStatus      # status after success
    checkpoint: str | None       # approval gate raised after success (if enabled)
    label: str


STAGES: list[StageSpec] = [
    StageSpec(Stage.SCRIPT, ProjectStatus.SOURCE_APPROVED, ProjectStatus.SCRIPT_READY, "story_adaptation", "Story bible & script"),
    StageSpec(Stage.CHARACTERS, ProjectStatus.SCRIPT_READY, ProjectStatus.CHARACTERS_READY, "character_generation", "Character reference sheets"),
    StageSpec(Stage.SCENES, ProjectStatus.CHARACTERS_READY, ProjectStatus.SCENES_READY, "scene_generation", "Scene illustrations"),
    StageSpec(Stage.AUDIO, ProjectStatus.SCENES_READY, ProjectStatus.AUDIO_READY, None, "Localization, voices & subtitles"),
    StageSpec(Stage.RENDER, ProjectStatus.AUDIO_READY, ProjectStatus.RENDERED, None, "Video rendering"),
    StageSpec(Stage.QC, ProjectStatus.RENDERED, ProjectStatus.QC_PASSED, "final_render", "Quality control"),
    StageSpec(Stage.PUBLISH, ProjectStatus.QC_APPROVED, ProjectStatus.UPLOADED, None, "YouTube publishing"),
]

SPEC_BY_STAGE = {s.stage: s for s in STAGES}
SPEC_BY_CHECKPOINT = {s.checkpoint: s for s in STAGES if s.checkpoint}


def next_stage(status: ProjectStatus | str) -> StageSpec | None:
    """The stage that moves a project forward from its current status."""
    status = ProjectStatus(status)
    if status is ProjectStatus.QC_PASSED:
        return None  # waiting on the final_render approval, not on a stage
    for spec in STAGES:
        if spec.requires is status:
            return spec
    return None


def can_run(stage: Stage, status: ProjectStatus | str) -> bool:
    """A stage may run (or re-run) once the project has reached its prerequisite."""
    status = ProjectStatus(status)
    if status is ProjectStatus.CANCELLED:
        return False
    spec = SPEC_BY_STAGE[stage]
    if stage is Stage.PUBLISH:
        return rank(status) >= rank(ProjectStatus.QC_APPROVED)
    return rank(status) >= rank(spec.requires)
