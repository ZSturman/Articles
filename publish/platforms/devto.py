"""DEV.to publishing client."""

import logging
import time

import requests

from .. import config
from ..discover import Article
from . import PlatformClient, PublishResult

logger = logging.getLogger(__name__)

BASE_URL = "https://dev.to/api"
MAX_RETRIES = 3


class DevToClient(PlatformClient):
    name = "devto"

    def __init__(self):
        self.api_key = config.DEVTO_API_KEY
        self.session = requests.Session()
        self.session.headers.update({
            "api-key": self.api_key,
            "Accept": "application/vnd.forem.api-v1+json",
            "Content-Type": "application/json",
        })

    def publish(self, article: Article, body: str, tags: list[str], cover_image_url: str) -> PublishResult:
        payload = self._build_payload(article, body, tags, cover_image_url)
        resp = self._request("POST", f"{BASE_URL}/articles", json=payload)
        data = resp.json()
        return PublishResult(
            post_id=str(data["id"]),
            url=data["url"],
            platform=self.name,
        )

    def update(self, article: Article, body: str, tags: list[str], cover_image_url: str, existing_id: str) -> PublishResult:
        payload = self._build_payload(article, body, tags, cover_image_url)
        resp = self._request("PUT", f"{BASE_URL}/articles/{existing_id}", json=payload)
        data = resp.json()
        return PublishResult(
            post_id=str(data["id"]),
            url=data["url"],
            platform=self.name,
        )

    def _build_payload(self, article: Article, body: str, tags: list[str], cover_image_url: str) -> dict:
        payload: dict = {
            "article": {
                "title": article.title,
                "body_markdown": body,
                "published": True,
                "canonical_url": article.canonical_url,
            }
        }
        if article.summary:
            payload["article"]["description"] = article.summary
        if tags:
            payload["article"]["tags"] = tags
        if cover_image_url:
            payload["article"]["main_image"] = cover_image_url
        if article.series:
            payload["article"]["series"] = article.series
        return payload

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        for attempt in range(MAX_RETRIES):
            resp = self.session.request(method, url, **kwargs)
            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", 2 ** attempt))
                logger.warning("DEV.to rate limited, retrying in %ds", retry_after)
                time.sleep(retry_after)
                continue
            if resp.status_code >= 500:
                wait = 2 ** attempt
                logger.warning("DEV.to server error %d, retrying in %ds", resp.status_code, wait)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp
        resp.raise_for_status()
        return resp
