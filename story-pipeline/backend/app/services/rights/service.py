"""Rights and provenance decisions.

The single most important rule in this codebase: nothing becomes
rights_status=approved without an explicit human decision that names a
license and the evidence for it. An LLM saying "this story is old" is not evidence.
"""
from __future__ import annotations

from datetime import UTC, datetime

from app.persistence.models import StorySource

# What each license type permits by default. Adjust after reading the actual license.
LICENSE_PRESETS: dict[str, list[str]] = {
    "public_domain": ["adaptation", "verbatim", "commercial"],
    "public_domain_us": ["adaptation", "verbatim", "commercial"],
    "cc0": ["adaptation", "verbatim", "commercial"],
    "cc_by": ["adaptation", "verbatim", "commercial", "attribution_required"],
    "cc_by_sa": ["adaptation", "verbatim", "commercial", "attribution_required", "share_alike"],
    "cc_by_nc": ["adaptation", "verbatim", "attribution_required", "non_commercial"],
    "cc_by_nd": ["verbatim", "commercial", "attribution_required"],      # no derivatives!
    "licensed": ["adaptation", "commercial"],
    "user_owned": ["adaptation", "verbatim", "commercial"],
    "inspiration_only": ["adaptation"],   # may inspire an original story; no close paraphrase
}
RIGHTS_STATUSES = {"pending", "approved", "rejected", "review_required"}


class RightsError(ValueError):
    pass


def decide(src: StorySource, *, status: str, license_type: str | None = None, allowed_uses: list[str] | None = None,
           evidence_url: str | None = None, notes: str | None = None, attribution: str | None = None,
           decided_by: str = "user") -> StorySource:
    if status not in RIGHTS_STATUSES:
        raise RightsError(f"status must be one of {sorted(RIGHTS_STATUSES)}")
    license_type = license_type or src.license_type
    if status == "approved":
        if not license_type or license_type == "unknown":
            raise RightsError("approval requires a license_type")
        if not (evidence_url or src.license_evidence_url or notes):
            raise RightsError("approval requires license evidence (a URL or written notes)")
        uses = allowed_uses if allowed_uses is not None else LICENSE_PRESETS.get(license_type, [])
        if "adaptation" not in uses:
            raise RightsError(f"license '{license_type}' does not permit adaptation; this pipeline adapts every story")
        if "attribution_required" in uses and not (attribution or src.attribution):
            raise RightsError("this license requires attribution text")
        src.allowed_uses = uses
    elif allowed_uses is not None:
        src.allowed_uses = allowed_uses
    src.rights_status = status
    src.license_type = license_type or "unknown"
    if evidence_url:
        src.license_evidence_url = evidence_url
    if notes:
        src.license_notes = notes
    if attribution:
        src.attribution = attribution
    src.rights_decided_by = decided_by
    src.rights_decided_at = datetime.now(UTC)
    return src


def assert_usable(src: StorySource) -> None:
    """Gate used by project creation and again right before publishing (rights can be revoked)."""
    if src.rights_status != "approved":
        raise RightsError(f"source '{src.title}' rights status is {src.rights_status}, not approved")
    if "adaptation" not in (src.allowed_uses or []):
        raise RightsError(f"source '{src.title}' is not cleared for adaptation")


def requires_transformation(src: StorySource) -> bool:
    """True when the script must not closely reproduce the source text."""
    return "verbatim" not in (src.allowed_uses or [])
