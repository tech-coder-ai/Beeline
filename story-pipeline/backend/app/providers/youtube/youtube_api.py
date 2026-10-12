"""YouTube Data API v3 publisher (videos.insert, thumbnails.set).

Install extras:  pip install -e ".[youtube]"
Authorize once:  python scripts/youtube_auth.py   (writes publishing.token_file)

Idempotency: every upload carries a tag `spa-<attempt>`. Before uploading,
find_existing() scans the channel's recent uploads for that tag, so a retry
after a network timeout does not create a duplicate video.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from app.providers.errors import ProviderError, ProviderUnavailable
from app.providers.youtube.base import UploadResult

SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.readonly"]


def attempt_tag(attempt_id: str) -> str:
    return f"spa-{attempt_id[-12:]}"


class YouTubeApiPublisher:
    name = "youtube"

    def __init__(self, token_file: Path):
        self.token_file = token_file
        self._service = None

    def _yt(self):
        if self._service is not None:
            return self._service
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
        except ImportError as exc:
            raise ProviderUnavailable('google-api-python-client not installed: pip install -e ".[youtube]"') from exc
        if not self.token_file.exists():
            raise ProviderUnavailable(f"no OAuth token at {self.token_file}; run scripts/youtube_auth.py")
        creds = Credentials.from_authorized_user_file(str(self.token_file), SCOPES)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            self.token_file.write_text(creds.to_json())
        self._service = build("youtube", "v3", credentials=creds, cache_discovery=False)
        return self._service

    @staticmethod
    def _wrap(exc: Exception) -> ProviderError:
        status = getattr(getattr(exc, "resp", None), "status", None)
        transient = status is None or int(status) >= 500 or int(status) == 429
        return ProviderError(f"YouTube API error ({status}): {exc}", transient=transient)

    def find_existing(self, attempt_id: str) -> UploadResult | None:
        yt = self._yt()
        tag = attempt_tag(attempt_id)
        try:
            ch = yt.channels().list(part="contentDetails", mine=True).execute()
            uploads = ch["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
            items = yt.playlistItems().list(part="contentDetails", playlistId=uploads, maxResults=25).execute()
            ids = [i["contentDetails"]["videoId"] for i in items.get("items", [])]
            if not ids:
                return None
            vids = yt.videos().list(part="snippet", id=",".join(ids)).execute()
        except Exception as exc:  # noqa: BLE001
            raise self._wrap(exc) from exc
        for v in vids.get("items", []):
            if tag in v["snippet"].get("tags", []):
                return UploadResult(v["id"], f"https://www.youtube.com/watch?v={v['id']}")
        return None

    def upload(self, video: Path, thumbnail: Path | None, metadata: dict[str, Any], attempt_id: str) -> UploadResult:
        from googleapiclient.http import MediaFileUpload

        yt = self._yt()
        body = {
            "snippet": {
                "title": metadata["title"],
                "description": metadata["description"],
                "tags": [*metadata.get("tags", []), attempt_tag(attempt_id)][:30],
                "categoryId": metadata.get("category_id", "1"),
                "defaultLanguage": metadata.get("language"),
                "defaultAudioLanguage": metadata.get("language"),
            },
            "status": {
                "privacyStatus": metadata.get("visibility", "private"),
                "selfDeclaredMadeForKids": bool(metadata.get("made_for_kids", False)),
                # YouTube's "altered or synthetic content" disclosure
                "containsSyntheticMedia": bool(metadata.get("synthetic", True)),
            },
        }
        try:
            req = yt.videos().insert(part="snippet,status", body=body,
                                     media_body=MediaFileUpload(str(video), chunksize=8 << 20, resumable=True))
            response = None
            while response is None:
                _, response = req.next_chunk()
            vid = response["id"]
            if thumbnail and thumbnail.exists():
                try:
                    yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(str(thumbnail))).execute()
                except Exception:  # noqa: BLE001 - custom thumbnails need a verified channel; not fatal
                    pass
        except ProviderError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise self._wrap(exc) from exc
        return UploadResult(vid, f"https://www.youtube.com/watch?v={vid}")

    def processing_status(self, video_id: str) -> str:
        try:
            r = self._yt().videos().list(part="processingDetails,status", id=video_id).execute()
        except Exception as exc:  # noqa: BLE001
            raise self._wrap(exc) from exc
        items = r.get("items", [])
        if not items:
            return "not_found"
        return items[0].get("processingDetails", {}).get("processingStatus", items[0]["status"].get("uploadStatus", "unknown"))

    def health(self) -> dict[str, Any]:
        try:
            self._yt()
            return {"ok": True, "detail": "authorized"}
        except ProviderError as exc:
            return {"ok": False, "detail": str(exc)}
