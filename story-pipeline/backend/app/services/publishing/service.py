"""Publish stage: idempotent uploads with reconciliation.

A network timeout does not prove YouTube rejected the upload. So:
  1. Every language gets ONE Publication row with a stable attempt_id.
  2. Before any upload attempt after the first, ask the platform whether a
     video carrying that attempt_id already exists (find_existing).
  3. Only then upload. Mark the row 'uploading' (committed) *before* the call,
     so a crash mid-upload is visible and reconciled on the next run.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from app.persistence.models import Approval, Asset, Project, Publication, RenderJob, StorySource
from app.providers.errors import ProviderError
from app.providers.registry import build_publisher
from app.services.rights.service import assert_usable
from app.workflow.context import StageContext, StageFailed

DONE = {"uploaded", "processing", "processed"}


def assert_publishable(db, project: Project, require_human: bool) -> None:
    """Backend gate - the API never trusts the UI to have checked this."""
    if project.status not in ("QC_APPROVED", "UPLOADED"):
        raise StageFailed(f"project must be QC_APPROVED to publish (is {project.status})")
    assert_usable(db.get(StorySource, project.source_id))
    latest = db.scalars(select(Approval).where(Approval.project_id == project.id, Approval.checkpoint == "final_render")
                        .order_by(Approval.created_at.desc())).first()
    if latest is None or latest.decision == "rejected":
        raise StageFailed("no final_render approval on record")
    if require_human and latest.decision != "approved":
        raise StageFailed("publishing.require_approval is on: a human must approve the final render")


def run_publish_stage(ctx: StageContext) -> dict:
    s = ctx.settings
    visibility = ctx.options.get("visibility") or s.publishing.default_visibility
    languages = ctx.options.get("languages")
    with ctx.db() as db:
        project = db.get(Project, ctx.project_id)
        assert_publishable(db, project, s.publishing.require_approval)
        targets = [(rj.id, rj.language) for rj in db.scalars(select(RenderJob).where(
            RenderJob.project_id == project.id, RenderJob.status == "rendered", RenderJob.qc_passed.is_(True)))
            if not languages or rj.language in languages]
    if not targets:
        raise StageFailed("no QC-passed renders to publish")
    publisher = build_publisher(s, ctx.assets.root)
    results: dict[str, str] = {}
    errors: list[ProviderError] = []
    for rj_id, code in targets:
        ctx.check_cancelled()
        ctx.progress(len(results) / len(targets), f"publishing {code}")
        with ctx.db() as db:
            rj = db.get(RenderJob, rj_id)
            pub = db.scalars(select(Publication).where(Publication.project_id == ctx.project_id,
                                                       Publication.render_job_id == rj_id)
                             .order_by(Publication.created_at.desc())).first()
            if pub and pub.status in DONE:
                results[code] = f"already published: {pub.url}"
                continue
            if pub is None:
                pub = Publication(project_id=ctx.project_id, language=code, render_job_id=rj_id,
                                  attempt_id=f"att_{uuid.uuid4().hex}", provider=publisher.name,
                                  visibility=visibility, metadata_={**rj.metadata_, "visibility": visibility},
                                  status="pending", retries=0)
                db.add(pub)
                db.flush()  # assign the primary key now
            needs_reconcile = pub.retries > 0 or pub.status in ("uploading", "failed")
            pub.status = "uploading"
            pub_id, attempt_id, meta = pub.id, pub.attempt_id, dict(pub.metadata_)
            video = ctx.assets.path_of(db.get(Asset, rj.video_asset_id))
            thumb = ctx.assets.path_of(db.get(Asset, rj.thumbnail_asset_id)) if rj.thumbnail_asset_id else None
        try:
            result = publisher.find_existing(attempt_id) if needs_reconcile else None
            reconciled = result is not None
            if result is None:
                result = publisher.upload(video, thumb, meta, attempt_id)
            status = publisher.processing_status(result.video_id)
        except ProviderError as exc:
            with ctx.db() as db:
                pub = db.get(Publication, pub_id)
                pub.status, pub.last_error, pub.retries = "failed", str(exc)[:2000], pub.retries + 1
            errors.append(exc)
            results[code] = f"failed: {exc}"
            continue
        with ctx.db() as db:
            pub = db.get(Publication, pub_id)
            pub.video_id, pub.url, pub.status, pub.processing_status = result.video_id, result.url, "uploaded", status
            pub.last_error, pub.confirmed_at = None, datetime.now(UTC)
        results[code] = f"{'reconciled' if reconciled else 'uploaded'} ({visibility}): {result.url}"
    if errors:
        raise ProviderError(f"{len(errors)} upload(s) failed: {errors[0]}", transient=all(e.transient for e in errors))
    return {"publications": results, "provider": publisher.name}
