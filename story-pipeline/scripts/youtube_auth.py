"""One-time OAuth consent for YouTube uploads.

1. Google Cloud console -> create a project -> enable "YouTube Data API v3".
2. Create an OAuth client ID of type "Desktop app"; download the JSON to
   story-pipeline/secrets/client_secret.json (path: publishing.client_secrets_file).
3. pip install -e "backend[youtube]"  then  python scripts/youtube_auth.py
4. Set publishing.provider: youtube  (or SPA_PUBLISH_PROVIDER=youtube).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from google_auth_oauthlib.flow import InstalledAppFlow  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.providers.youtube.youtube_api import SCOPES  # noqa: E402

settings = get_settings()
secrets = settings.path(settings.publishing.client_secrets_file)
token = settings.path(settings.publishing.token_file)
flow = InstalledAppFlow.from_client_secrets_file(str(secrets), SCOPES)
creds = flow.run_local_server(port=0)
token.parent.mkdir(parents=True, exist_ok=True)
token.write_text(creds.to_json())
print(f"Saved token to {token}")
