"""Medium publishing client (deprecated API — best effort)."""

import logging
import time

import requests

from .. import config
from ..discover import Article
from . import PlatformClient, PublishResult

logger = logging.getLogger(__name__)

BASE_URL = "https://api.medium.com/v1"
MAX_RETRIES = 3


class MediumClient(PlatformClient):
    name = "medium"

    def __init__(self):
        self.token = config.MEDIUM_TOKEN
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        })
        self._user_id: str | None = None

    @property
    def supports_update(self) -> bool:
        return False

    def publish(self, article: Article, body: str, tags: list[str], cover_image_url: str) -> PublishResult:
        user_id = self._get_user_id()
        payload = {
            "title": article.title,
            "contentFormat": "markdown",
            "content": f"# {article.title}\n\n{body}",
            "canonicalUrl": article.canonical_url,
            "publishStatus": "draft",
        }
        if tags:
            # Medium: max 5 tags, 25 chars each
            payload["tags"] = [t[:25] for t in tags[:5]]

        resp = self._request("POST", f"{BASE_URL}/users/{user_id}/posts", json=payload)
        data = resp.json().get("data", {})
        return PublishResult(
            post_id=data.get("id", ""),
            url=data.get("url", ""),
            platform=self.name,
        )

    def update(self, article: Article, body: str, tags: list[str], cover_image_url: str, existing_id: str) -> PublishResult:
        raise NotImplementedError(
            "Medium API does not support updating posts. "
            "The article was previously published as a draft — edit it manually on medium.com."
        )

    def _get_user_id(self) -> str:
        if self._user_id:
            return self._user_id
        resp = self._request("GET", f"{BASE_URL}/me")
        self._user_id = resp.json()["data"]["id"]
        return self._user_id

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        for attempt in range(MAX_RETRIES):
            resp = self.session.request(method, url, **kwargs)
            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", 2 ** attempt))
                logger.warning("Medium rate limited, retrying in %ds", retry_after)
                time.sleep(retry_after)
                continue
            if resp.status_code >= 500:
                wait = 2 ** attempt
                logger.warning("Medium server error %d, retrying in %ds", resp.status_code, wait)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp
        resp.raise_for_status()
        return resp
