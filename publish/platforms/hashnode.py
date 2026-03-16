"""Hashnode publishing client (GraphQL API)."""

import logging
import time

import requests

from .. import config
from ..discover import Article
from . import PlatformClient, PublishResult

logger = logging.getLogger(__name__)

API_URL = "https://gql.hashnode.com"
MAX_RETRIES = 3


CREATE_POST_MUTATION = """
mutation PublishPost($input: PublishPostInput!) {
  publishPost(input: $input) {
    post {
      id
      url
    }
  }
}
"""

UPDATE_POST_MUTATION = """
mutation UpdatePost($input: UpdatePostInput!) {
  updatePost(input: $input) {
    post {
      id
      url
    }
  }
}
"""

SEARCH_TAGS_QUERY = """
query SearchTags($keyword: String!) {
  searchTags(input: { keyword: $keyword, limit: 1 }) {
    nodes {
      id
      name
      slug
    }
  }
}
"""


class HashnodeClient(PlatformClient):
    name = "hashnode"

    def __init__(self):
        self.token = config.HASHNODE_TOKEN
        self.publication_id = config.HASHNODE_PUBLICATION_ID
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": self.token,
            "Content-Type": "application/json",
        })
        self._tag_cache: dict[str, dict] = {}

    def publish(self, article: Article, body: str, tags: list[str], cover_image_url: str) -> PublishResult:
        tag_ids = self._resolve_tags(tags)
        variables = {
            "input": {
                "publicationId": self.publication_id,
                "title": article.title,
                "contentMarkdown": body,
                "originalArticleURL": article.canonical_url,
                "tags": tag_ids,
            }
        }
        if article.summary:
            variables["input"]["subtitle"] = article.summary
        if cover_image_url:
            variables["input"]["coverImageOptions"] = {"coverImageURL": cover_image_url}

        data = self._graphql(CREATE_POST_MUTATION, variables)
        post = data["data"]["publishPost"]["post"]
        return PublishResult(
            post_id=post["id"],
            url=post["url"],
            platform=self.name,
        )

    def update(self, article: Article, body: str, tags: list[str], cover_image_url: str, existing_id: str) -> PublishResult:
        tag_ids = self._resolve_tags(tags)
        variables = {
            "input": {
                "id": existing_id,
                "title": article.title,
                "contentMarkdown": body,
                "originalArticleURL": article.canonical_url,
                "tags": tag_ids,
            }
        }
        if article.summary:
            variables["input"]["subtitle"] = article.summary
        if cover_image_url:
            variables["input"]["coverImageOptions"] = {"coverImageURL": cover_image_url}

        data = self._graphql(UPDATE_POST_MUTATION, variables)
        post = data["data"]["updatePost"]["post"]
        return PublishResult(
            post_id=post["id"],
            url=post["url"],
            platform=self.name,
        )

    def _resolve_tags(self, tags: list[str]) -> list[dict]:
        """Resolve tag strings to Hashnode tag objects {id, name, slug}.

        Searches the Hashnode API for each tag. Unrecognized tags are skipped
        with a warning rather than failing the publish.
        """
        resolved = []
        for tag_name in tags:
            if tag_name in self._tag_cache:
                resolved.append(self._tag_cache[tag_name])
                continue
            try:
                data = self._graphql(SEARCH_TAGS_QUERY, {"keyword": tag_name})
                nodes = data.get("data", {}).get("searchTags", {}).get("nodes", [])
                if nodes:
                    tag_obj = {"id": nodes[0]["id"], "name": nodes[0]["name"], "slug": nodes[0]["slug"]}
                    self._tag_cache[tag_name] = tag_obj
                    resolved.append(tag_obj)
                else:
                    logger.warning("Hashnode tag '%s' not found, skipping", tag_name)
            except Exception:
                logger.warning("Failed to resolve Hashnode tag '%s', skipping", tag_name, exc_info=True)
        return resolved

    def _graphql(self, query: str, variables: dict) -> dict:
        payload = {"query": query, "variables": variables}
        for attempt in range(MAX_RETRIES):
            resp = self.session.post(API_URL, json=payload)
            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", 2 ** attempt))
                logger.warning("Hashnode rate limited, retrying in %ds", retry_after)
                time.sleep(retry_after)
                continue
            if resp.status_code >= 500:
                wait = 2 ** attempt
                logger.warning("Hashnode server error %d, retrying in %ds", resp.status_code, wait)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            data = resp.json()
            if "errors" in data:
                error_msg = "; ".join(e.get("message", str(e)) for e in data["errors"])
                raise RuntimeError(f"Hashnode GraphQL error: {error_msg}")
            return data
        resp.raise_for_status()
        return resp.json()
