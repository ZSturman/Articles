#!/usr/bin/env python3
"""
Pre-push validation for article files.

Ensures every article has correct folder naming, file structure, and
valid YAML frontmatter with all required fields before allowing a push.

Exit codes:
  0 — all articles valid
  1 — one or more validation errors found
"""

from __future__ import annotations

import os
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import unquote

# ── Constants (mirrored from SYNC-ARTICLES.py) ──────────────────────────────

REPO_ROOT = Path(__file__).parent
MARKDOWN_INDEX_NAMES = {"index.md", "index.markdown"}
MARKDOWN_FILE_EXTS = {".md", ".markdown"}
FRONTMATTER_BOUNDARY = "---"

REQUIRED_FRONTMATTER_FIELDS = ["title", "summary"]

# Directories / files that are never articles
IGNORED_NAMES = {
    ".git", ".github", ".venv", "__pycache__", "node_modules",
    "publish", "public", "build", "dist",
}
IGNORED_FILES = {
    "README.md", "readme.md", "CHANGELOG.md", "LICENSE.md",
    "SYNC-ARTICLES.py", "validate-articles.py", "fix-articles.py",
    "requirements.txt", ".gitignore", ".env",
    ".publish-state.json",
}

MEDIA_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico",
    ".mp4", ".mov", ".webm", ".ogg", ".mp3", ".wav",
    ".pdf",
}

SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")
MARKDOWN_LINK_RE = re.compile(
    r"(?P<prefix>!?\[[^\]]*\]\()(?P<target>(?:[^()\n]|\([^)]*\))+)(?P<suffix>\))"
)
HTML_ATTR_RE = re.compile(
    r'(?P<attr>\b(?:src|href)=)(?P<quote>["\'])(?P<target>[^"\']+)(?P=quote)'
)

# ── Slug normalisation (same logic as SYNC-ARTICLES.py) ─────────────────────

def normalize_slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    lowered = ascii_only.strip().lower().replace("_", "-")
    lowered = lowered.replace("/", "-")
    lowered = re.sub(r"[^a-z0-9\s-]", "", lowered)
    lowered = re.sub(r"[\s-]+", "-", lowered).strip("-")
    return lowered or "article"


# ── Frontmatter parsing (same logic as SYNC-ARTICLES.py) ────────────────────

def _strip_quotes(value: str) -> str:
    trimmed = value.strip()
    if len(trimmed) >= 2 and trimmed[0] == trimmed[-1] and trimmed[0] in {"'", '"'}:
        return trimmed[1:-1]
    return trimmed


def _parse_inline_list(value: str) -> List[str]:
    inner = value.strip()[1:-1].strip()
    if not inner:
        return []
    items: List[str] = []
    current: List[str] = []
    quote_char: Optional[str] = None
    for char in inner:
        if quote_char:
            if char == quote_char:
                quote_char = None
            else:
                current.append(char)
            continue
        if char in {"'", '"'}:
            quote_char = char
            continue
        if char == ",":
            items.append(_strip_quotes("".join(current)))
            current = []
            continue
        current.append(char)
    items.append(_strip_quotes("".join(current)))
    return [item for item in (entry.strip() for entry in items) if item]


def parse_frontmatter_block(block: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    current_key: Optional[str] = None
    for raw_line in block.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("- "):
            if current_key is None:
                continue
            existing = result.setdefault(current_key, [])
            if not isinstance(existing, list):
                continue
            existing.append(_strip_quotes(stripped[2:].strip()))
            continue
        if ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        key = key.strip()
        value = raw_value.strip()
        if not key:
            continue
        if not value:
            result[key] = None
            current_key = key
            continue
        if value.startswith("[") and value.endswith("]"):
            result[key] = _parse_inline_list(value)
        else:
            result[key] = _strip_quotes(value)
        current_key = None
    return result


def split_frontmatter(text: str) -> Tuple[Optional[Dict[str, Any]], Optional[str], List[str]]:
    """Parse frontmatter from text. Returns (metadata, body, errors)."""
    errors: List[str] = []

    if not text.startswith(FRONTMATTER_BOUNDARY):
        return None, None, ["Missing YAML frontmatter (file must start with ---)"]

    normalized = text.replace("\r\n", "\n")
    lines = normalized.split("\n")
    if not lines or lines[0].strip() != FRONTMATTER_BOUNDARY:
        return None, None, ["Frontmatter must begin with --- on the first line"]

    closing_index = None
    for idx, line in enumerate(lines[1:], start=1):
        if line.strip() == FRONTMATTER_BOUNDARY:
            closing_index = idx
            break

    if closing_index is None:
        return None, None, ["Frontmatter is missing a closing --- delimiter"]

    fm_block = "\n".join(lines[1:closing_index])
    body = "\n".join(lines[closing_index + 1:]).lstrip("\n")
    metadata = parse_frontmatter_block(fm_block)
    return metadata, body, errors


# ── Discovery ────────────────────────────────────────────────────────────────

def _is_article_candidate_dir(entry: Path) -> bool:
    if entry.name.startswith("."):
        return False
    if entry.name.lower() in {n.lower() for n in IGNORED_NAMES}:
        return False
    return True


def _is_article_candidate_file(entry: Path) -> bool:
    if entry.name in IGNORED_FILES:
        return False
    if entry.name.startswith("."):
        return False
    return entry.suffix.lower() in MARKDOWN_FILE_EXTS


def discover_articles(repo_root: Path) -> List[Dict[str, Any]]:
    """Find all article sources, same logic as SYNC-ARTICLES.py."""
    articles: List[Dict[str, Any]] = []

    search_roots: List[Path] = []
    articles_dir = repo_root / "articles"
    if articles_dir.exists() and articles_dir.is_dir():
        search_roots.append(articles_dir)
    search_roots.append(repo_root)

    for search_root in search_roots:
        if not search_root.exists():
            continue
        for entry in sorted(search_root.iterdir(), key=lambda p: p.name.lower()):
            if entry.is_dir() and _is_article_candidate_dir(entry):
                # Directory-layout article
                index_path = None
                for candidate in MARKDOWN_INDEX_NAMES:
                    cp = entry / candidate
                    if cp.exists():
                        index_path = cp
                        break
                articles.append({
                    "path": entry,
                    "layout": "directory",
                    "folder_name": entry.name,
                    "index_path": index_path,
                    "slug": normalize_slug(entry.name),
                })
            elif entry.is_file() and _is_article_candidate_file(entry):
                # Standalone-file article
                articles.append({
                    "path": entry,
                    "layout": "file",
                    "folder_name": None,
                    "index_path": entry,
                    "slug": normalize_slug(entry.stem),
                })
    return articles


# ── Validation ───────────────────────────────────────────────────────────────

def validate_slug_format(name: str) -> List[str]:
    """Check that a folder/file name already matches the normalised slug."""
    errors: List[str] = []
    expected = normalize_slug(name)
    if name != expected:
        errors.append(
            f"Name \"{name}\" does not match the expected slug format. "
            f"Rename to \"{expected}\""
        )
    if re.search(r"[A-Z]", name):
        errors.append(f"Name \"{name}\" contains uppercase characters — use lowercase only")
    if "_" in name:
        errors.append(f"Name \"{name}\" contains underscores — use hyphens instead")
    if re.search(r"[^a-z0-9\-]", name):
        errors.append(f"Name \"{name}\" contains disallowed characters — only a-z, 0-9, and hyphens")
    return errors


def validate_frontmatter(metadata: Dict[str, Any], slug: str) -> List[str]:
    errors: List[str] = []
    for field in REQUIRED_FRONTMATTER_FIELDS:
        val = metadata.get(field)
        if val is None:
            errors.append(f"Missing required frontmatter field: {field}")
        elif isinstance(val, str) and not val.strip():
            errors.append(f"Frontmatter field \"{field}\" is present but empty")
    # At least one date field required
    has_published = metadata.get("publishedAt") and str(metadata["publishedAt"]).strip()
    has_updated = metadata.get("updatedAt") and str(metadata["updatedAt"]).strip()
    if not has_published and not has_updated:
        errors.append("Missing required frontmatter: need at least publishedAt or updatedAt")
    # Optional field type checks
    tags = metadata.get("tags")
    if tags is not None and not isinstance(tags, list):
        errors.append("Field \"tags\" should be a YAML list (e.g. [tag1, tag2] or list items)")
    project_ids = metadata.get("projectIds")
    if project_ids is not None and not isinstance(project_ids, list):
        errors.append("Field \"projectIds\" should be a YAML list")
    return errors


def _is_relative_target(target: str) -> bool:
    stripped = target.strip()
    if not stripped:
        return False
    if stripped.startswith(("/", "#", "mailto:", "tel:", "data:")):
        return False
    return not SCHEME_RE.match(stripped)


def validate_media(
    markdown: str, *, index_path: Path, article_root: Path
) -> List[str]:
    """Check that all embedded media references point to existing files."""
    errors: List[str] = []
    seen: set[str] = set()

    def check_target(raw_target: str) -> None:
        target_path, _frag = raw_target.strip().split("#", 1) if "#" in raw_target else (raw_target.strip(), "")
        if not _is_relative_target(target_path):
            return
        decoded = unquote(target_path)
        ext = Path(decoded).suffix.lower()
        if ext not in MEDIA_EXTS:
            return
        if target_path in seen:
            return
        seen.add(target_path)
        resolved = (index_path.parent / decoded).resolve()
        if not resolved.exists():
            errors.append(f"Missing media: {decoded} (referenced in markdown)")
        elif not os.access(resolved, os.R_OK):
            errors.append(f"Media not readable: {decoded}")

    for m in MARKDOWN_LINK_RE.finditer(markdown):
        check_target(m.group("target"))
    for m in HTML_ATTR_RE.finditer(markdown):
        check_target(m.group("target"))
    return errors


def validate_article(article: Dict[str, Any]) -> List[str]:
    """Run all validations for a single article. Returns list of error strings."""
    errors: List[str] = []
    layout = article["layout"]
    slug = article["slug"]

    # 1. Folder/file name slug format
    if layout == "directory":
        errors.extend(validate_slug_format(article["folder_name"]))
    else:
        stem = article["path"].stem
        slug_errors = validate_slug_format(stem)
        errors.extend(slug_errors)

    # 2. Index markdown must exist for directory articles
    if layout == "directory" and article["index_path"] is None:
        errors.append(
            f"Directory \"{article['folder_name']}\" is missing index.md — "
            "create an index.md file inside this folder"
        )
        return errors  # Can't check frontmatter without a file

    index_path: Path = article["index_path"]
    if not index_path.exists():
        errors.append(f"Markdown file not found: {index_path}")
        return errors

    # 3. Read and validate frontmatter
    try:
        text = index_path.read_text(encoding="utf-8")
    except Exception as exc:
        errors.append(f"Cannot read {index_path}: {exc}")
        return errors

    # Strip BOM
    text = text.lstrip("\ufeff")

    metadata, body, parse_errors = split_frontmatter(text)
    errors.extend(parse_errors)

    if metadata is not None:
        errors.extend(validate_frontmatter(metadata, slug))

    # 4. Validate embedded media files exist and are readable
    content_to_scan = body if body else text
    article_root = article["path"] if layout == "directory" else article["path"].parent
    media_errors = validate_media(content_to_scan, index_path=index_path, article_root=article_root)
    errors.extend(media_errors)

    return errors


# ── Main ─────────────────────────────────────────────────────────────────────

RESET = "\033[0m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BOLD = "\033[1m"
CYAN = "\033[36m"


def main() -> int:
    repo_root = REPO_ROOT

    print(f"\n{BOLD}{'=' * 60}{RESET}")
    print(f"{BOLD}  Article Validation (pre-push check){RESET}")
    print(f"{BOLD}{'=' * 60}{RESET}\n")

    articles = discover_articles(repo_root)

    if not articles:
        print(f"{YELLOW}No articles found in repository.{RESET}")
        print(f"{GREEN}Push allowed.{RESET}\n")
        return 0

    total_errors = 0
    article_results: List[Tuple[str, str, List[str]]] = []

    for article in articles:
        label = article["folder_name"] or article["path"].name
        layout = article["layout"]
        errors = validate_article(article)
        article_results.append((label, layout, errors))
        total_errors += len(errors)

    # Print results
    for label, layout, errors in article_results:
        layout_tag = "dir " if layout == "directory" else "file"
        if errors:
            print(f"  {RED}FAIL{RESET}  [{layout_tag}] {BOLD}{label}{RESET}")
            for err in errors:
                print(f"        {RED}>{RESET} {err}")
        else:
            print(f"  {GREEN} OK {RESET}  [{layout_tag}] {BOLD}{label}{RESET}")

    print()

    if total_errors > 0:
        print(f"{BOLD}{'─' * 60}{RESET}")
        print(f"{RED}{BOLD}  PUSH BLOCKED — {total_errors} error(s) found{RESET}")
        print(f"{BOLD}{'─' * 60}{RESET}")
        print()
        print(f"  {CYAN}Required frontmatter format:{RESET}")
        print(f"  {CYAN}┌────────────────────────────────────┐{RESET}")
        print(f"  {CYAN}│  ---                               │{RESET}")
        print(f"  {CYAN}│  title: \"Your Article Title\"       │{RESET}")
        print(f"  {CYAN}│  summary: \"Brief description\"      │{RESET}")
        print(f"  {CYAN}│  publishedAt: \"2025-01-15\"         │{RESET}")
        print(f"  {CYAN}│  tags: [tag1, tag2]                │{RESET}")
        print(f"  {CYAN}│  ---                               │{RESET}")
        print(f"  {CYAN}└────────────────────────────────────┘{RESET}")
        print()
        print(f"  {CYAN}Folder naming rules:{RESET}")
        print(f"    - lowercase only")
        print(f"    - hyphens instead of underscores or spaces")
        print(f"    - only a-z, 0-9, and hyphens")
        print(f"    - directory articles must contain index.md")
        print(f"    - all embedded images/media must exist")
        print()
        print(f"  {CYAN}Try running:{RESET}  python3 fix-articles.py --dry-run")
        print(f"  {CYAN}Then apply:{RESET}   python3 fix-articles.py")
        print()
        return 1

    print(f"{GREEN}{BOLD}  All {len(articles)} article(s) valid — push allowed{RESET}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
