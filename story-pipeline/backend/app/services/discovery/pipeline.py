"""Discover -> fetch -> extract -> normalize -> deduplicate -> rank -> store (pending rights review)."""
from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.persistence.models import StorySource
from app.services.discovery.connectors import Candidate, Connector, GutendexConnector, LocalLibraryConnector, RssConnector

GUTENBERG_START = re.compile(r"\*\*\*\s*START OF (THE|THIS) PROJECT GUTENBERG EBOOK.*?\*\*\*", re.I | re.S)
GUTENBERG_END = re.compile(r"\*\*\*\s*END OF (THE|THIS) PROJECT GUTENBERG EBOOK.*", re.I | re.S)


def connectors(settings: Settings) -> dict[str, Connector]:
    d = settings.discovery
    return {
        "library": LocalLibraryConnector(settings.path(d.library_dir)),
        "gutenberg": GutendexConnector(d),
        "rss": RssConnector(d),
    }


# --------------------------------------------------------------- text cleanup
def extract(text: str) -> str:
    """Strip boilerplate (Gutenberg header/footer, HTML remnants) but keep chapter headings."""
    m = GUTENBERG_START.search(text)
    if m:
        text = text[m.end():]
    text = GUTENBERG_END.sub("", text)
    text = re.sub(r"<[^>]+>", " ", text)
    return text


def normalize(text: str) -> str:
    """Canonical form used for hashing and downstream processing."""
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.translate({0x2018: "'", 0x2019: "'", 0x201C: '"', 0x201D: '"', 0x2014: " - ", 0x2013: "-"})
    text = re.sub(r"[ \t]+", " ", text)
    # unwrap hard-wrapped lines inside paragraphs, keep blank-line paragraph breaks
    paras = [re.sub(r"\s*\n\s*", " ", p).strip() for p in re.split(r"\n\s*\n", text)]
    return "\n\n".join(p for p in paras if p)


def content_hash(text: str) -> str:
    # hash a whitespace/case-insensitive form so trivial reformatting is still a duplicate
    canon = re.sub(r"\W+", " ", text.lower()).strip()
    return hashlib.sha256(canon.encode()).hexdigest()


def shingles(text: str, k: int = 6) -> set[str]:
    words = re.findall(r"\w+", text.lower())
    return {" ".join(words[i:i + k]) for i in range(max(0, len(words) - k + 1))}


def jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


# -------------------------------------------------------------------- ranking
def rank(text: str, suggested_license: str | None) -> tuple[float, dict]:
    """A transparent 0-100 score. Tune weights for your channel; every part is shown in the UI."""
    words = len(text.split())
    if 150 <= words <= 3000:
        length = 35.0
    elif words < 150:
        length = 35.0 * words / 150
    else:
        length = max(5.0, 35.0 * 3000 / words)  # long works need episode splitting = more cost
    quotes = len(re.findall(r"\"[^\"]{3,}\"|'[^']{12,}'", text))
    dialogue = min(20.0, quotes * 4.0)
    names = {m for m in re.findall(r"(?<=[a-z,;] )([A-Z][a-z]{2,})", text)}
    cast = min(20.0, len(names) * 5.0)
    rights = {"public_domain": 25.0, "public_domain_us": 22.0, "cc_by": 20.0, "cc_by_sa": 18.0,
              "user_owned": 25.0, "licensed": 25.0}.get(suggested_license or "", 0.0)
    breakdown = {"length": round(length, 1), "dialogue": round(dialogue, 1), "cast": round(cast, 1),
                 "rights_clarity": rights, "word_count": words}
    return round(length + dialogue + cast + rights, 1), breakdown


def synopsis_of(text: str, max_words: int = 60) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    out: list[str] = []
    for s in sentences:
        if sum(len(x.split()) for x in out) + len(s.split()) > max_words and out:
            break
        out.append(s)
    return " ".join(out)


# ------------------------------------------------------------------ ingestion
@dataclass
class IngestResult:
    source: StorySource | None
    status: str           # created | duplicate | near_duplicate | empty
    detail: str = ""


def ingest(db: Session, settings: Settings, cand: Candidate, text: str | None = None) -> IngestResult:
    raw = text if text is not None else (cand.text or "")
    clean = normalize(extract(raw))[: settings.discovery.max_story_chars]
    if len(clean.split()) < 30:
        return IngestResult(None, "empty", "less than 30 words after extraction")
    h = content_hash(clean)
    existing = db.scalars(select(StorySource).where(StorySource.content_hash == h)).first()
    if existing:
        return IngestResult(existing, "duplicate", f"same content as {existing.id}")
    sh = shingles(clean)
    for other in db.scalars(select(StorySource)):
        sim = jaccard(sh, shingles(other.text))
        if sim > 0.8:
            return IngestResult(other, "near_duplicate", f"{sim:.0%} similar to {other.id} ({other.title})")
    score, breakdown = rank(clean, cand.suggested_license)
    src = StorySource(
        connector=cand.connector, external_id=cand.external_id, title=cand.title[:300], author=cand.author,
        source_url=cand.source_url, published=cand.published, language=cand.language, category=cand.category,
        text=clean, synopsis=synopsis_of(clean), word_count=len(clean.split()), content_hash=h,
        suggested_license=cand.suggested_license, license_evidence_url=cand.license_evidence_url,
        license_notes=cand.license_notes, attribution=cand.attribution,
        # A license claim exists -> a human must verify it. No claim -> pending research.
        rights_status="review_required" if cand.suggested_license else "pending",
        score=score, score_breakdown=breakdown,
    )
    db.add(src)
    db.flush()
    return IngestResult(src, "created")


def discover(db: Session, settings: Settings, connector_name: str, query: str, limit: int) -> list[IngestResult]:
    conns = connectors(settings)
    if connector_name not in conns:
        raise ValueError(f"unknown connector '{connector_name}' (have {sorted(conns)})")
    conn = conns[connector_name]
    results = []
    for cand in conn.search(query, limit):
        try:
            text = conn.fetch(cand)
        except Exception as exc:  # noqa: BLE001 - one bad source shouldn't abort discovery
            results.append(IngestResult(None, "error", f"{cand.title}: {exc}"))
            continue
        results.append(ingest(db, settings, cand, text))
    return results
