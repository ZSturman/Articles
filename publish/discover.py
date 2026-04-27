"""Discover articles from the repo's folder-per-article structure."""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import frontmatter

from . import config


READY_STATUS = "ready to post"


@dataclass
class Article:
    slug: str
    title: str
    body: str
    canonical_url: str
    summary: str = ""
    tags: list[str] = field(default_factory=list)
    cover_image: str = ""
    series: str = ""
    status: str = "draft"
    raw_frontmatter: dict = field(default_factory=dict)
    source_path: Path = field(default_factory=lambda: Path("."))

    @property
    def is_ready_to_post(self) -> bool:
        return self.status.strip().lower() == READY_STATUS

    @property
    def index_path(self) -> Path:
        return self.source_path / "index.md"


def _extract_first_h1(body: str) -> str:
    """Pull the first # heading from markdown body as a fallback title."""
    match = re.search(r"^#\s+\**(.+?)\**\s*$", body, re.MULTILINE)
    return match.group(1).strip() if match else ""


def _serialize_frontmatter(metadata: dict[str, Any]) -> str:
    """Serialize metadata using the repo's existing simple frontmatter style."""
    lines = ["---"]
    for key, value in metadata.items():
        if isinstance(value, list):
            items = ", ".join(str(item) for item in value)
            lines.append(f"{key}: [{items}]")
        elif value is None:
            continue
        else:
            text = str(value)
            if ":" in text or text.startswith(("{", "[", '"', "'")):
                lines.append(f'{key}: "{text}"')
            else:
                lines.append(f"{key}: {text}")
    lines.append("---")
    return "\n".join(lines)


def ensure_published_at(article: "Article", published_at: str) -> bool:
    """Persist publishedAt to an article file if it is currently missing."""
    existing = article.raw_frontmatter.get("publishedAt")
    if existing is not None and str(existing).strip():
        return False

    updated_metadata = dict(article.raw_frontmatter)
    updated_metadata["publishedAt"] = published_at

    frontmatter_text = _serialize_frontmatter(updated_metadata)
    body = article.body.lstrip("\n")
    serialized = frontmatter_text if not body else f"{frontmatter_text}\n\n{body}"
    article.index_path.write_text(serialized + "\n", encoding="utf-8")
    article.raw_frontmatter = updated_metadata
    return True


def discover_articles(repo_root: Path, slugs: list[str] | None = None) -> list[Article]:
    """Scan repo root for article folders containing index.md.

    If slugs is provided, only discover those specific articles.
    """
    articles = []
    candidates = sorted(repo_root.iterdir()) if slugs is None else [repo_root / s for s in slugs]

    for folder in candidates:
        if not folder.is_dir():
            continue
        index_file = folder / "index.md"
        if not index_file.exists():
            continue
        # Skip non-article directories (like publish/, .github/, etc.)
        if folder.name.startswith(".") or folder.name == "publish":
            continue

        article = _parse_article(folder, index_file)
        if article:
            articles.append(article)

    return articles


def _parse_article(folder: Path, index_file: Path) -> Article | None:
    """Parse an index.md file into an Article, tolerating any frontmatter shape."""
    try:
        post = frontmatter.load(str(index_file))
    except Exception:
        return None

    meta = dict(post.metadata)
    body = post.content
    slug = folder.name

    # Title: frontmatter > first H1 > slug
    title = meta.get("title", "") or _extract_first_h1(body) or slug

    # Canonical URL: frontmatter > derived from slug
    canonical_url = meta.get("canonical_url", "") or f"{config.CANONICAL_BASE_URL}/{slug}"

    # Tags: accept list or comma-separated string
    raw_tags = meta.get("tags", [])
    if isinstance(raw_tags, str):
        tags = [t.strip() for t in raw_tags.split(",") if t.strip()]
    elif isinstance(raw_tags, list):
        tags = [str(t).strip() for t in raw_tags if str(t).strip()]
    else:
        tags = []

    return Article(
        slug=slug,
        title=title,
        body=body,
        canonical_url=canonical_url,
        summary=meta.get("summary", "") or meta.get("description", ""),
        tags=tags,
        cover_image=meta.get("cover_image", ""),
        series=meta.get("series", ""),
        status=str(meta.get("status", "draft")).strip(),
        raw_frontmatter=meta,
        source_path=folder,
    )
