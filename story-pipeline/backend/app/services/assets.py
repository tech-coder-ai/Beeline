"""Managed asset registry: every generated file is written here and recorded as an Asset row."""
from __future__ import annotations

import mimetypes
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import Settings
from app.media import sha256_file
from app.persistence.models import Asset


def project_dir(settings: Settings, project_id: str) -> Path:
    return settings.data_dir / "projects" / project_id


class AssetStore:
    def __init__(self, settings: Settings, project_id: str):
        self.settings = settings
        self.project_id = project_id
        self.root = project_dir(settings, project_id)
        self.root.mkdir(parents=True, exist_ok=True)

    def abs(self, rel_path: str) -> Path:
        p = (self.root / rel_path).resolve()
        if self.root.resolve() not in p.parents and p != self.root.resolve():
            raise ValueError(f"asset path escapes project dir: {rel_path}")
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def path_of(self, asset: Asset) -> Path:
        return self.root / asset.rel_path

    def is_valid(self, db: Session, asset_id: str | None) -> bool:
        """An asset is reusable only if its row exists AND the file is still on disk, intact."""
        if not asset_id:
            return False
        asset = db.get(Asset, asset_id)
        if asset is None:
            return False
        p = self.path_of(asset)
        return p.exists() and p.stat().st_size == asset.size_bytes

    def write_bytes(self, db: Session, kind: str, rel_path: str, data: bytes, **meta) -> Asset:
        p = self.abs(rel_path)
        tmp = p.with_suffix(p.suffix + ".part")
        tmp.write_bytes(data)
        tmp.replace(p)  # atomic: a crash never leaves a half-written file under the real name
        return self.register(db, kind, rel_path, **meta)

    def register(self, db: Session, kind: str, rel_path: str, *, provider: str | None = None,
                 model: str | None = None, prompt: str | None = None, seed: int | None = None,
                 meta: dict | None = None) -> Asset:
        p = self.abs(rel_path)
        asset = Asset(
            project_id=self.project_id, kind=kind, rel_path=rel_path,
            mime_type=mimetypes.guess_type(p.name)[0] or "application/octet-stream",
            checksum=sha256_file(p), size_bytes=p.stat().st_size,
            provider=provider, model=model, prompt=prompt, seed=seed, meta=meta or {},
        )
        db.add(asset)
        db.flush()
        return asset
