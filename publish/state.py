"""Publish state tracking via .publish-state.json."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


STATE_FILE = ".publish-state.json"


class PublishState:
    """Manages the .publish-state.json file that tracks what has been published."""

    def __init__(self, repo_root: Path):
        self.path = repo_root / STATE_FILE
        self._data: dict = {}
        self.load()

    def load(self):
        if self.path.exists():
            try:
                self._data = json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self._data = {}
        else:
            self._data = {}

    def save(self):
        self.path.write_text(
            json.dumps(self._data, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def content_hash(self, index_path: Path) -> str:
        """SHA-256 hash of the full index.md file contents."""
        content = index_path.read_bytes()
        return hashlib.sha256(content).hexdigest()

    def is_published(self, slug: str, platform: str) -> bool:
        """Check if an article has ever been published to a platform."""
        return platform in self._data.get(slug, {})

    def needs_update(self, slug: str, current_hash: str) -> bool:
        """Check if the article content has changed since last publish."""
        stored = self._data.get(slug, {}).get("content_hash", "")
        return stored != current_hash

    def get_platform_id(self, slug: str, platform: str) -> str | None:
        """Get the stored platform-specific ID for a published article."""
        return self._data.get(slug, {}).get(platform, {}).get("id")

    def get_platform_url(self, slug: str, platform: str) -> str | None:
        """Get the stored platform URL for a published article."""
        return self._data.get(slug, {}).get(platform, {}).get("url")

    def record_publish(self, slug: str, platform: str, post_id: str, url: str, content_hash: str):
        """Record a successful publish or update."""
        if slug not in self._data:
            self._data[slug] = {}
        self._data[slug]["content_hash"] = content_hash
        self._data[slug][platform] = {
            "id": post_id,
            "url": url,
            "published_at": datetime.now(timezone.utc).isoformat(),
        }

    def all_slugs(self) -> list[str]:
        """Return all slugs that have any publish state."""
        return list(self._data.keys())
