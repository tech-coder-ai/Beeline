"""Source connectors. Each one knows how to find candidates and fetch permitted text.

Connectors only *suggest* a license (what the source claims). They never set
rights_status = approved - that is a human decision recorded by the rights service.
"""
from __future__ import annotations

import json
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import httpx

from app.config import DiscoveryCfg


@dataclass
class Candidate:
    connector: str
    title: str
    author: str | None = None
    external_id: str | None = None
    source_url: str | None = None
    published: str | None = None
    language: str = "en"
    category: str = "public_domain_archive"
    text: str | None = None
    suggested_license: str | None = None
    license_evidence_url: str | None = None
    license_notes: str | None = None
    attribution: str | None = None
    fetch_url: str | None = None
    extra: dict = field(default_factory=dict)


class Connector(Protocol):
    name: str

    def search(self, query: str, limit: int) -> list[Candidate]: ...

    def fetch(self, candidate: Candidate) -> str: ...


class LocalLibraryConnector:
    """Curated stories shipped as JSON files - the safest, fully offline source."""
    name = "library"

    def __init__(self, library_dir: Path):
        self.library_dir = library_dir

    def _load(self) -> list[Candidate]:
        out = []
        for p in sorted(self.library_dir.glob("*.json")):
            d = json.loads(p.read_text(encoding="utf-8"))
            out.append(Candidate(
                connector=self.name, external_id=p.stem, title=d["title"], author=d.get("author"),
                source_url=d.get("source_url"), published=d.get("published"), language=d.get("language", "en"),
                category=d.get("category", "public_domain_archive"), text=d["text"],
                suggested_license=d.get("license_type"), license_evidence_url=d.get("license_evidence_url"),
                license_notes=d.get("license_notes"), attribution=d.get("attribution"),
            ))
        return out

    def search(self, query: str, limit: int) -> list[Candidate]:
        q = query.lower().strip()
        items = [c for c in self._load() if not q or q in c.title.lower() or q in (c.author or "").lower()
                 or q in (c.text or "").lower()]
        return items[:limit]

    def fetch(self, candidate: Candidate) -> str:
        return candidate.text or ""


class GutendexConnector:
    """Project Gutenberg via the Gutendex JSON API. Only books flagged copyright=false are requested.

    Gutenberg's "public domain in the USA" flag is evidence, not a guarantee for
    your jurisdiction - which is why the result is `review_required`, not approved.
    """
    name = "gutenberg"

    def __init__(self, cfg: DiscoveryCfg):
        self.cfg = cfg
        self._last_request = 0.0

    def _get(self, url: str, **params) -> httpx.Response:
        wait = self.cfg.request_delay_seconds - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)  # be a polite client: rate limit ourselves
        self._last_request = time.monotonic()
        r = httpx.get(url, params=params or None, headers={"User-Agent": self.cfg.user_agent},
                      timeout=30, follow_redirects=True)
        r.raise_for_status()
        return r

    def search(self, query: str, limit: int) -> list[Candidate]:
        data = self._get(f"{self.cfg.gutendex_url.rstrip('/')}/books", search=query, copyright="false",
                         languages="en").json()
        out = []
        for b in data.get("results", [])[:limit]:
            fmt = b.get("formats", {})
            txt = next((u for k, u in fmt.items() if k.startswith("text/plain")), None)
            if not txt:
                continue
            authors = ", ".join(a["name"] for a in b.get("authors", []))
            out.append(Candidate(
                connector=self.name, external_id=str(b["id"]), title=b["title"], author=authors or None,
                source_url=f"https://www.gutenberg.org/ebooks/{b['id']}", language=(b.get("languages") or ["en"])[0],
                suggested_license="public_domain_us",
                license_evidence_url=f"https://www.gutenberg.org/ebooks/{b['id']}",
                license_notes="Gutendex reports copyright=false (public domain in the USA). Verify for your jurisdiction; "
                              "remove Project Gutenberg trademark/license text if redistributing.",
                attribution=f"{b['title']} by {authors or 'Unknown'} (Project Gutenberg #{b['id']})",
                fetch_url=txt,
            ))
        return out

    def fetch(self, candidate: Candidate) -> str:
        if not candidate.fetch_url:
            return candidate.text or ""
        return self._get(candidate.fetch_url).text


class RssConnector:
    """RSS/Atom feeds you have permission to use. Only the feed's own summary/content is taken."""
    name = "rss"

    def __init__(self, cfg: DiscoveryCfg):
        self.cfg = cfg

    def search(self, query: str, limit: int) -> list[Candidate]:
        out: list[Candidate] = []
        for feed in self.cfg.rss_feeds:
            r = httpx.get(feed, headers={"User-Agent": self.cfg.user_agent}, timeout=30, follow_redirects=True)
            r.raise_for_status()
            root = ET.fromstring(r.content)
            items = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
            for it in items:
                def t(tag: str) -> str:
                    el = it.find(tag)
                    if el is None:
                        el = it.find("{http://www.w3.org/2005/Atom}" + tag)
                    return (el.text or "").strip() if el is not None and el.text else ""
                title, body = t("title"), t("description") or t("content") or t("summary")
                link_el = it.find("link")
                link = (link_el.text if link_el is not None and link_el.text else
                        (link_el.get("href") if link_el is not None else None))
                if query and query.lower() not in (title + body).lower():
                    continue
                out.append(Candidate(connector=self.name, title=title or "Untitled", source_url=link,
                                     category="rss_feed", text=re.sub(r"<[^>]+>", " ", body),
                                     suggested_license=None,
                                     license_notes=f"From feed {feed}; confirm reuse permission with the publisher."))
                if len(out) >= limit:
                    return out
        return out

    def fetch(self, candidate: Candidate) -> str:
        return candidate.text or ""
