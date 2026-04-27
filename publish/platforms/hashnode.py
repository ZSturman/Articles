"""Hashnode publishing client (GraphQL API)."""

import logging
import re
import time
from urllib.parse import urlparse

import requests

from .. import config
from ..discover import Article
from . import PlatformClient, PublishResult

logger = logging.getLogger(__name__)

API_URL = "https://gql.hashnode.com"
MAX_RETRIES = 3
MAX_SUBTITLE_LENGTH = 250
OBJECT_ID_RE = re.compile(r"^[0-9a-fA-F]{24}$")


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

ME_PUBLICATIONS_QUERY = """
query MePublications {
  me {
    id
    username
    publications(first: 20) {
      edges {
        node {
          id
          title
          url
          canonicalURL
          domainInfo {
            hashnodeSubdomain
            domain {
              host
              ready
            }
            wwwPrefixedDomain {
              host
              ready
            }
          }
        }
      }
    }
  }
}
"""


def _extract_host(value: str) -> str | None:
    candidate = (value or "").strip()
    if not candidate:
        return None
    if "://" not in candidate:
        candidate = f"https://{candidate}"
    parsed = urlparse(candidate)
    if parsed.netloc:
        return parsed.netloc.lower()
    path = parsed.path.strip().strip("/").lower()
    return path or None


def _slugify_tag(tag_name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", tag_name.lower()).strip("-")


class HashnodeClient(PlatformClient):
    name = "hashnode"

    def __init__(self):
        self.token = config.HASHNODE_TOKEN
        self.publication_id = config.HASHNODE_PUBLICATION_ID
        self._resolved_publication_id: str | None = None
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": self.token,
            "Content-Type": "application/json",
        })

    def publish(self, article: Article, body: str, tags: list[str], cover_image_url: str) -> PublishResult:
        tag_inputs = self._build_tags(tags)
        variables = {
            "input": {
                "publicationId": self._publication_id(),
                "title": article.title,
                "contentMarkdown": body,
                "originalArticleURL": article.canonical_url,
                "tags": tag_inputs,
            }
        }
        subtitle = self._subtitle(article.summary)
        if subtitle:
            variables["input"]["subtitle"] = subtitle
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
        tag_inputs = self._build_tags(tags)
        variables = {
            "input": {
                "id": existing_id,
                "title": article.title,
                "contentMarkdown": body,
                "originalArticleURL": article.canonical_url,
                "tags": tag_inputs,
            }
        }
        subtitle = self._subtitle(article.summary)
        if subtitle:
            variables["input"]["subtitle"] = subtitle
        if cover_image_url:
            variables["input"]["coverImageOptions"] = {"coverImageURL": cover_image_url}

        data = self._graphql(UPDATE_POST_MUTATION, variables)
        post = data["data"]["updatePost"]["post"]
        return PublishResult(
            post_id=post["id"],
            url=post["url"],
            platform=self.name,
        )

    def _publication_id(self) -> str:
        if self._resolved_publication_id:
            return self._resolved_publication_id

        publication_ref = self.publication_id.strip()
        if not publication_ref:
            raise RuntimeError("HASHNODE_PUBLICATION_ID is required to publish to Hashnode")
        if OBJECT_ID_RE.fullmatch(publication_ref):
            self._resolved_publication_id = publication_ref
            return publication_ref

        resolved_id = self._resolve_publication_id(publication_ref)
        logger.info("Resolved Hashnode publication reference %r to %s", publication_ref, resolved_id)
        self._resolved_publication_id = resolved_id
        return resolved_id

    def _resolve_publication_id(self, publication_ref: str) -> str:
        data = self._graphql(ME_PUBLICATIONS_QUERY, {})
        me = data.get("data", {}).get("me") or {}
        publications = [
            edge["node"]
            for edge in me.get("publications", {}).get("edges", [])
            if edge.get("node")
        ]
        if not publications:
            raise RuntimeError("Hashnode token did not return any publications")

        publication = self._match_publication(publication_ref, me.get("username", ""), publications)
        if publication:
            return publication["id"]
        if len(publications) == 1:
            return publications[0]["id"]

        available = ", ".join(self._publication_label(item) for item in publications)
        raise RuntimeError(
            "Could not resolve HASHNODE_PUBLICATION_ID to one of the authenticated user's publications. "
            f"Set it to a publication ObjectId or hostname. Available publications: {available}"
        )

    def _match_publication(self, publication_ref: str, username: str, publications: list[dict]) -> dict | None:
        normalized_ref = publication_ref.strip()
        normalized_username = (username or "").strip().lower()

        candidate_host: str | None = None
        candidate_username: str | None = None

        if normalized_ref.startswith("@"):
            candidate_username = normalized_ref[1:].strip().lower()
        elif "://" in normalized_ref:
            parsed = urlparse(normalized_ref)
            if parsed.netloc.lower() == "hashnode.com":
                path = parsed.path.strip().strip("/")
                if path.startswith("@"):
                    candidate_username = path[1:].strip().lower()
                else:
                    candidate_host = parsed.netloc.lower()
            else:
                candidate_host = (parsed.netloc or "").lower() or None
        elif "." in normalized_ref or "/" in normalized_ref:
            candidate_host = _extract_host(normalized_ref)
        else:
            candidate_username = normalized_ref.lower()

        if candidate_host:
            for publication in publications:
                if candidate_host in self._publication_hosts(publication):
                    return publication

        if candidate_username:
            for publication in publications:
                hosts = self._publication_hosts(publication)
                if candidate_username in hosts or f"{candidate_username}.hashnode.dev" in hosts:
                    return publication
            if candidate_username == normalized_username and len(publications) == 1:
                return publications[0]

        return None

    def _publication_hosts(self, publication: dict) -> set[str]:
        hosts: set[str] = set()
        for value in (publication.get("url"), publication.get("canonicalURL")):
            host = _extract_host(value or "")
            if host:
                hosts.add(host)

        domain_info = publication.get("domainInfo") or {}
        hashnode_subdomain = (domain_info.get("hashnodeSubdomain") or "").strip().lower()
        if hashnode_subdomain:
            hosts.add(hashnode_subdomain)
            hosts.add(f"{hashnode_subdomain}.hashnode.dev")

        for key in ("domain", "wwwPrefixedDomain"):
            host = ((domain_info.get(key) or {}).get("host") or "").strip().lower()
            if host:
                hosts.add(host)

        return hosts

    def _publication_label(self, publication: dict) -> str:
        hosts = sorted(self._publication_hosts(publication))
        primary = hosts[0] if hosts else publication.get("title", "<unknown>")
        return f"{primary} ({publication['id']})"

    def _build_tags(self, tags: list[str]) -> list[dict]:
        """Build Hashnode tag inputs using stable local slugification."""
        resolved = []
        seen_slugs: set[str] = set()
        for tag_name in tags:
            clean_name = tag_name.strip()
            slug = _slugify_tag(clean_name)
            if not clean_name or not slug or slug in seen_slugs:
                continue
            resolved.append({"name": clean_name, "slug": slug})
            seen_slugs.add(slug)
        return resolved

    def _subtitle(self, summary: str | None) -> str | None:
        if not summary:
            return None
        clean_summary = summary.strip()
        if len(clean_summary) <= MAX_SUBTITLE_LENGTH:
            return clean_summary

        truncated = clean_summary[:MAX_SUBTITLE_LENGTH].rsplit(" ", 1)[0].rstrip()
        logger.warning("Hashnode subtitle exceeds %d characters, truncating", MAX_SUBTITLE_LENGTH)
        return truncated or clean_summary[:MAX_SUBTITLE_LENGTH]

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
            data = None
            try:
                data = resp.json()
            except ValueError:
                data = None
            if isinstance(data, dict) and "errors" in data:
                error_msg = "; ".join(e.get("message", str(e)) for e in data["errors"])
                raise RuntimeError(f"Hashnode GraphQL error: {error_msg}")
            resp.raise_for_status()
            if data is None:
                data = resp.json()
            return data
        resp.raise_for_status()
        return resp.json()
