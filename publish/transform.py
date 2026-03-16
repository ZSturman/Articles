"""Transform article markdown for each publishing platform."""

import re
from urllib.parse import quote, unquote

from . import config
from .discover import Article


def _encode_path(raw_path: str) -> str:
    """URL-encode a path, handling already-encoded paths correctly.

    Decodes first to avoid double-encoding (%20 → %2520), then re-encodes.
    """
    decoded = unquote(raw_path)
    return quote(decoded, safe="/")


def _rewrite_image_urls(body: str, slug: str) -> str:
    """Rewrite relative image/asset paths to absolute GitHub raw URLs.

    Handles both markdown images ![alt](path) and HTML <img src="path">.
    Skips URLs that are already absolute (http/https).
    """
    raw_base = config.github_raw_base()

    def _rewrite_md_image(match: re.Match) -> str:
        alt = match.group(1)
        path = match.group(2)
        if path.startswith(("http://", "https://", "//")):
            return match.group(0)
        clean_path = path.lstrip("./")
        encoded_path = _encode_path(clean_path)
        return f"![{alt}]({raw_base}/{slug}/{encoded_path})"

    def _rewrite_html_img(match: re.Match) -> str:
        prefix = match.group(1)
        path = match.group(2)
        suffix = match.group(3)
        if path.startswith(("http://", "https://", "//")):
            return match.group(0)
        clean_path = path.lstrip("./")
        encoded_path = _encode_path(clean_path)
        return f'{prefix}{raw_base}/{slug}/{encoded_path}{suffix}'

    # Markdown images: ![alt](path)
    body = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", _rewrite_md_image, body)
    # HTML images: <img src="path" or <img src='path'
    body = re.sub(r'(<img\s[^>]*src=["\'])([^"\']+)(["\'][^>]*>)', _rewrite_html_img, body)

    return body


def _strip_leading_h1(body: str, title: str) -> str:
    """Remove the first H1 heading if it matches the article title.

    Platforms render their own title, so a duplicate H1 looks wrong.
    """
    # Match first H1 (possibly bold-wrapped) at start of content
    pattern = r"^\s*#\s+\**" + re.escape(title.strip().rstrip("*").lstrip("*")) + r"\**\s*\n*"
    return re.sub(pattern, "", body, count=1).lstrip("\n")


def transform_for_platform(article: Article, platform: str) -> str:
    """Return the article body transformed for a specific platform."""
    body = article.body
    body = _rewrite_image_urls(body, article.slug)
    body = _strip_leading_h1(body, article.title)
    return body


def tags_for_platform(article: Article, platform: str) -> list[str]:
    """Return tags adjusted for platform constraints."""
    tags = list(article.tags)
    if platform == "medium":
        # Medium: max 5 tags, 25 chars each
        tags = [t[:25] for t in tags[:5]]
    if platform == "devto":
        # DEV.to: max 4 tags, lowercase, alphanumeric/hyphens only
        cleaned = []
        for t in tags[:4]:
            tag = re.sub(r"[^a-z0-9-]", "", t.lower().replace(" ", "-"))
            if tag:
                cleaned.append(tag)
        tags = cleaned
    return tags


def cover_image_url(article: Article) -> str:
    """Resolve cover_image to an absolute URL if it's a relative path."""
    if not article.cover_image:
        return ""
    if article.cover_image.startswith(("http://", "https://")):
        return article.cover_image
    clean_path = article.cover_image.lstrip("./")
    encoded_path = _encode_path(clean_path)
    return f"{config.github_raw_base()}/{article.slug}/{encoded_path}"
