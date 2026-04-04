#!/usr/bin/env python3
"""
Auto-fix article files for SYNC-ARTICLES.py compatibility.

Handles:
- Converting Notion-style metadata headers to YAML frontmatter
- Renaming folders/files to match the expected slug format
- Fixing broken media/image paths by searching for files by name
- Reports what it cannot fix automatically (missing required values)

Usage:
  python3 fix-articles.py            # apply fixes
  python3 fix-articles.py --dry-run  # preview without writing
"""

from __future__ import annotations

import argparse
from datetime import date
import os
import re
import shutil
import sys
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import unquote

# ── Constants ────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).parent
MARKDOWN_INDEX_NAMES = {"index.md", "index.markdown"}
MARKDOWN_FILE_EXTS = {".md", ".markdown"}
FRONTMATTER_BOUNDARY = "---"

# Required by SYNC-ARTICLES.py
REQUIRED_FIELDS = ["title", "summary"]

# Notion metadata keys that map to frontmatter fields
NOTION_KEY_MAP = {
    "summary": "summary",
    "tags": "tags",
    "series": "series",
    "cover image": "coverImage",
    "link to repo": "repoUrl",
}

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

# Pattern for plausible Notion metadata keys: letters, digits, spaces,
# underscores, hyphens, question marks.  No commas, periods, or parens.
_META_KEY_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9 _?\-]*$")
_META_KEY_MAX_LEN = 30

# ── Colours ──────────────────────────────────────────────────────────────────

RESET = "\033[0m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BOLD = "\033[1m"
CYAN = "\033[36m"
DIM = "\033[2m"

# ── Slug normalisation ──────────────────────────────────────────────────────

def normalize_slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    lowered = ascii_only.strip().lower().replace("_", "-")
    lowered = lowered.replace("/", "-")
    lowered = re.sub(r"[^a-z0-9\s-]", "", lowered)
    lowered = re.sub(r"[\s-]+", "-", lowered).strip("-")
    return lowered or "article"


# ── Discovery (mirrors validate-articles.py) ────────────────────────────────

def _is_article_dir(entry: Path) -> bool:
    if entry.name.startswith("."):
        return False
    return entry.name.lower() not in {n.lower() for n in IGNORED_NAMES}


def _is_article_file(entry: Path) -> bool:
    if entry.name in IGNORED_FILES or entry.name.startswith("."):
        return False
    return entry.suffix.lower() in MARKDOWN_FILE_EXTS


def discover_articles(repo_root: Path) -> List[Dict[str, Any]]:
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
            if entry.is_dir() and _is_article_dir(entry):
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
            elif entry.is_file() and _is_article_file(entry):
                articles.append({
                    "path": entry,
                    "layout": "file",
                    "folder_name": None,
                    "index_path": entry,
                    "slug": normalize_slug(entry.stem),
                })
    return articles


# ── Notion metadata detection & extraction ───────────────────────────────────

def _looks_like_notion_metadata(text: str) -> bool:
    """Heuristic: file starts with # heading followed by key: value lines."""
    stripped = text.lstrip("\ufeff")
    if stripped.startswith(FRONTMATTER_BOUNDARY):
        return False
    lines = stripped.split("\n")
    if not lines:
        return False
    # Must start with a heading
    has_heading = lines[0].startswith("# ")
    # Scan for key: value lines, skipping blank lines after heading
    kv_count = 0
    past_blanks = False
    for line in lines[1:40]:  # scan first 40 lines
        if not line.strip():
            if past_blanks and kv_count > 0:
                break  # blank line after kv section = end of header
            continue
        past_blanks = True
        if ":" in line and not line.startswith("#"):
            kv_count += 1
        else:
            break
    return has_heading and kv_count >= 2


def _parse_notion_header(text: str) -> Tuple[Dict[str, str], str]:
    """
    Parse a Notion-export-style header into key-value pairs and body.
    Returns (raw_kv_dict, body_text).
    The first # heading becomes the 'title' key.
    The header extends until the next # heading (which starts the article body).
    Key-value lines (key portion <= 40 chars) are captured as metadata.
    Non-KV text is preserved as pre-body content.
    """
    lines = text.lstrip("\ufeff").replace("\r\n", "\n").split("\n")
    kv: Dict[str, str] = {}
    body_start = 0
    pre_body_text: List[str] = []

    # Extract title from heading
    if lines and lines[0].startswith("# "):
        kv["title"] = lines[0][2:].strip()
        body_start = 1

    # Skip blank lines between heading and key-value section
    while body_start < len(lines) and not lines[body_start].strip():
        body_start += 1

    # Scan until the next # heading — everything before it is metadata.
    for i, line in enumerate(lines[body_start:], start=body_start):
        stripped = line.strip()

        # Next heading = start of article body
        if stripped.startswith("# "):
            body_start = i
            break

        # Blank line: skip
        if not stripped:
            continue

        # Key-value line: short key that looks like a metadata field name
        if ":" in stripped:
            key_part = stripped.split(":", 1)[0].strip()
            if len(key_part) <= _META_KEY_MAX_LEN and _META_KEY_RE.match(key_part):
                kv[key_part] = stripped.split(":", 1)[1].strip()
                continue

        # Non-KV prose: preserve for prepending to body
        pre_body_text.append(stripped)
    else:
        body_start = len(lines)

    # Skip blank lines between header and body
    while body_start < len(lines) and not lines[body_start].strip():
        body_start += 1

    body = "\n".join(lines[body_start:])
    # Prepend any non-KV prose found in the header section
    if pre_body_text:
        body = "\n\n".join(pre_body_text) + "\n\n" + body
    return kv, body


# Keys where comma-separated values should become YAML lists
COMMA_LIST_KEYS = {"tags", "platform"}

# Notion key names that should be normalised to match the publish system
NOTION_KEY_NORMALIZE: Dict[str, str] = {
    "cover image": "cover_image",
    "coverimage": "cover_image",
    "coverImage": "cover_image",
    "cover-image": "cover_image",
}


def _build_frontmatter_from_notion(raw_kv: Dict[str, str]) -> Dict[str, Any]:
    """
    Convert Notion-style raw key-values to frontmatter dict.
    Preserves ALL key-value pairs from the Notion header.
    Only applies special formatting where the data clearly warrants it
    (e.g. comma-separated tags become a YAML list).
    Normalises known key names to match the publish system.
    """
    fm: Dict[str, Any] = {}
    for key, value in raw_kv.items():
        if not value:
            continue
        # Normalise known key variants
        norm_key = NOTION_KEY_NORMALIZE.get(key, None) or NOTION_KEY_NORMALIZE.get(key.lower(), key)
        if norm_key.lower() in COMMA_LIST_KEYS:
            items = [t.strip() for t in value.split(",") if t.strip()]
            fm[norm_key] = items if items else value
        else:
            fm[norm_key] = value
    return fm


def _serialize_frontmatter(fm: Dict[str, Any]) -> str:
    """Serialize a frontmatter dict to YAML-style text with --- delimiters."""
    lines = [FRONTMATTER_BOUNDARY]
    for key, value in fm.items():
        if isinstance(value, list):
            items = ", ".join(value)
            lines.append(f"{key}: [{items}]")
        elif value is None:
            continue
        else:
            # Quote values that contain colons or special chars
            str_val = str(value)
            if ":" in str_val or str_val.startswith(("{", "[", '"', "'")):
                lines.append(f'{key}: "{str_val}"')
            else:
                lines.append(f"{key}: {str_val}")
    lines.append(FRONTMATTER_BOUNDARY)
    return "\n".join(lines)


# ── Media path fixing ────────────────────────────────────────────────────────

def _is_relative_target(target: str) -> bool:
    stripped = target.strip()
    if not stripped:
        return False
    if stripped.startswith(("/", "#", "mailto:", "tel:", "data:")):
        return False
    return not SCHEME_RE.match(stripped)


def _extract_fragment(target: str) -> Tuple[str, str]:
    if "#" not in target:
        return target, ""
    path_part, fragment = target.split("#", 1)
    return path_part, f"#{fragment}"


def _find_file_by_name(filename: str, search_root: Path) -> Optional[Path]:
    """Recursively search for a file by name, preferring shallower matches."""
    lower_name = filename.lower()
    candidates: List[Path] = []
    for path in sorted(search_root.rglob("*")):
        if path.is_file() and path.name.lower() == lower_name:
            candidates.append(path)
    if not candidates:
        return None
    return min(candidates, key=lambda p: len(p.relative_to(search_root).parts))


def _fix_media_paths_in_markdown(
    markdown: str,
    *,
    markdown_path: Path,
    article_root: Path,
) -> Tuple[str, List[str], List[str]]:
    """
    Rewrite broken relative media paths by searching for files by name.
    Returns (rewritten_markdown, list_of_fixes, list_of_missing).
    """
    fixes: List[str] = []
    missing: List[str] = []

    def fix_target(raw_target: str) -> Optional[str]:
        target, fragment = _extract_fragment(raw_target.strip())
        if not _is_relative_target(target):
            return None

        decoded = unquote(target)
        resolved = (markdown_path.parent / decoded).resolve()
        if resolved.exists():
            return None  # Already valid

        # Is it a media file?
        filename = Path(decoded).name
        ext = Path(filename).suffix.lower()
        if ext not in MEDIA_EXTS:
            return None  # Not media, don't touch

        # Search for it in the article directory
        found = _find_file_by_name(filename, article_root)
        if found is None:
            missing.append(f"{filename} (referenced as {raw_target.strip()})")
            return None

        # Compute correct relative path from markdown file to found file
        try:
            rel = os.path.relpath(found, markdown_path.parent)
        except ValueError:
            return None
        new_target = rel.replace(os.sep, "/") + fragment
        fixes.append(f"{raw_target.strip()} -> {new_target}")
        return new_target

    def replace_md_link(match: re.Match[str]) -> str:
        replacement = fix_target(match.group("target"))
        if replacement is None:
            return match.group(0)
        return f"{match.group('prefix')}{replacement}{match.group('suffix')}"

    def replace_html_attr(match: re.Match[str]) -> str:
        replacement = fix_target(match.group("target"))
        if replacement is None:
            return match.group(0)
        return f"{match.group('attr')}{match.group('quote')}{replacement}{match.group('quote')}"

    rewritten = MARKDOWN_LINK_RE.sub(replace_md_link, markdown)
    rewritten = HTML_ATTR_RE.sub(replace_html_attr, rewritten)
    return rewritten, fixes, missing


# ── Collect all embedded media for validation ────────────────────────────────

def collect_media_references(
    markdown: str, *, markdown_path: Path
) -> List[Tuple[str, Path]]:
    """
    Return list of (raw_target, resolved_path) for every relative media ref.
    """
    refs: List[Tuple[str, Path]] = []
    seen: set[str] = set()

    def process(raw_target: str) -> None:
        target, _frag = _extract_fragment(raw_target.strip())
        if not _is_relative_target(target):
            return
        decoded = unquote(target)
        ext = Path(decoded).suffix.lower()
        if ext not in MEDIA_EXTS:
            return
        if target in seen:
            return
        seen.add(target)
        resolved = (markdown_path.parent / decoded).resolve()
        refs.append((raw_target.strip(), resolved))

    for m in MARKDOWN_LINK_RE.finditer(markdown):
        process(m.group("target"))
    for m in HTML_ATTR_RE.finditer(markdown):
        process(m.group("target"))
    return refs


# ── Per-article fix logic ────────────────────────────────────────────────────

def fix_article(article: Dict[str, Any], *, dry_run: bool) -> Tuple[List[str], List[str], List[str]]:
    """
    Attempt to fix an article. Returns (actions_taken, warnings, errors).
    actions = things that were (or would be) changed
    warnings = things user should review
    errors = things that can't be auto-fixed
    """
    actions: List[str] = []
    warnings: List[str] = []
    errors: List[str] = []
    layout = article["layout"]
    slug = article["slug"]

    # ── 1. Folder / file rename ──────────────────────────────────────────
    if layout == "directory":
        current_name = article["folder_name"]
        expected_name = normalize_slug(current_name)
        if current_name != expected_name:
            old_path = article["path"]
            new_path = old_path.parent / expected_name
            if new_path.exists():
                errors.append(
                    f"Cannot rename \"{current_name}\" to \"{expected_name}\" — "
                    f"target already exists"
                )
            else:
                actions.append(f"Rename folder: {current_name} -> {expected_name}")
                if not dry_run:
                    old_path.rename(new_path)
                    # Update article dict for subsequent steps
                    article["path"] = new_path
                    article["folder_name"] = expected_name
                    article["slug"] = expected_name
                    if article["index_path"] is not None:
                        rel = article["index_path"].relative_to(old_path)
                        article["index_path"] = new_path / rel
    else:
        current_stem = article["path"].stem
        expected_stem = normalize_slug(current_stem)
        if current_stem != expected_stem:
            old_path = article["path"]
            new_path = old_path.parent / f"{expected_stem}{old_path.suffix}"
            if new_path.exists():
                errors.append(
                    f"Cannot rename \"{old_path.name}\" to \"{new_path.name}\" — "
                    f"target already exists"
                )
            else:
                actions.append(f"Rename file: {old_path.name} -> {new_path.name}")
                if not dry_run:
                    old_path.rename(new_path)
                    article["path"] = new_path
                    article["index_path"] = new_path
                    article["slug"] = expected_stem

    # ── 2. Check index.md exists ─────────────────────────────────────────
    if layout == "directory" and article["index_path"] is None:
        errors.append(
            f"Directory \"{article['folder_name']}\" has no index.md — "
            "create one manually"
        )
        return actions, warnings, errors

    index_path: Path = article["index_path"]
    if not index_path.exists():
        errors.append(f"File not found: {index_path}")
        return actions, warnings, errors

    # ── 3. Read content ──────────────────────────────────────────────────
    try:
        text = index_path.read_text(encoding="utf-8")
    except Exception as exc:
        errors.append(f"Cannot read {index_path}: {exc}")
        return actions, warnings, errors

    clean_text = text.lstrip("\ufeff")
    article_root = article["path"] if layout == "directory" else article["path"].parent
    content_changed = False

    # ── 4. Convert Notion metadata to frontmatter ────────────────────────
    if not clean_text.startswith(FRONTMATTER_BOUNDARY):
        if _looks_like_notion_metadata(clean_text):
            raw_kv, body = _parse_notion_header(clean_text)
            fm = _build_frontmatter_from_notion(raw_kv)

            if not fm:
                errors.append("Detected Notion-style header but could not extract any fields")
            else:
                extracted = ", ".join(fm.keys())
                actions.append(f"Convert Notion metadata to frontmatter (extracted: {extracted})")

                # Check which required fields are still missing (case-insensitive)
                fm_keys_lower = {k.lower() for k in fm}
                for field in REQUIRED_FIELDS:
                    if field.lower() not in fm_keys_lower:
                        warnings.append(
                            f"Required field \"{field}\" not found in Notion metadata — "
                            f"you must add it manually to the frontmatter"
                        )

                # Auto-add updatedAt if neither publishedAt nor updatedAt exists
                has_published = any(k.lower() == "publishedat" for k in fm)
                has_updated = any(k.lower() == "updatedat" for k in fm)
                if not has_published and not has_updated:
                    today = date.today().isoformat()
                    fm["updatedAt"] = today
                    actions.append(f"Added updatedAt: {today} (no date field found)")

                fm_text = _serialize_frontmatter(fm)
                clean_text = fm_text + "\n\n" + body
                content_changed = True
        else:
            errors.append(
                "File is missing frontmatter (does not start with ---) and "
                "does not look like a recognisable Notion export"
            )

    # ── 4b. Auto-add updatedAt to existing frontmatter if no date field ──
    if clean_text.startswith(FRONTMATTER_BOUNDARY):
        normalized = clean_text.replace("\r\n", "\n")
        lines = normalized.split("\n")
        closing_idx = None
        for idx, line in enumerate(lines[1:], start=1):
            if line.strip() == FRONTMATTER_BOUNDARY:
                closing_idx = idx
                break
        if closing_idx is not None:
            fm_block = "\n".join(lines[1:closing_idx])
            fm_lower = fm_block.lower()
            has_pub = "publishedat:" in fm_lower
            has_upd = "updatedat:" in fm_lower
            if not has_pub and not has_upd:
                today = date.today().isoformat()
                lines.insert(closing_idx, f"updatedAt: {today}")
                clean_text = "\n".join(lines)
                content_changed = True
                actions.append(f"Added updatedAt: {today} (no date field found)")

    # ── 4c. Recover orphaned Notion metadata from body ────────────────────
    #     If frontmatter exists but key-value lines leaked into the body
    #     (between closing --- and the first # heading), move them back.
    #     Only scans a limited window (30 lines) to avoid touching real content.
    if clean_text.startswith(FRONTMATTER_BOUNDARY):
        normalized_c = clean_text.replace("\r\n", "\n")
        c_lines = normalized_c.split("\n")
        close_idx = None
        for idx, line in enumerate(c_lines[1:], start=1):
            if line.strip() == FRONTMATTER_BOUNDARY:
                close_idx = idx
                break
        if close_idx is not None:
            # Scan a limited window after the closing ---
            scan_end = min(close_idx + 30, len(c_lines))
            orphan_kv: List[Tuple[int, str, str]] = []  # (line_idx, key, value)
            for bi in range(close_idx + 1, scan_end):
                stripped = c_lines[bi].strip()
                if stripped.startswith("# "):
                    break
                if not stripped:
                    continue
                # Is it a key: value pair with a plausible metadata key?
                if ":" in stripped:
                    key_part = stripped.split(":", 1)[0].strip()
                    if len(key_part) <= _META_KEY_MAX_LEN and _META_KEY_RE.match(key_part):
                        v = stripped.split(":", 1)[1].strip()
                        orphan_kv.append((bi, key_part, v))

            if orphan_kv:
                # Insert orphaned KV pairs into frontmatter (before closing ---)
                insert_lines = []
                for _, k, v in orphan_kv:
                    norm_k = NOTION_KEY_NORMALIZE.get(k, None) or NOTION_KEY_NORMALIZE.get(k.lower(), k)
                    if ":" in v or v.startswith(("{", "[", '"', "'")):
                        insert_lines.append(f'{norm_k}: "{v}"')
                    else:
                        insert_lines.append(f"{norm_k}: {v}")
                    actions.append(f"Recover orphaned metadata: {k} -> frontmatter")

                # Remove only the orphaned KV lines from body (reverse order)
                for li, _, _ in sorted(orphan_kv, key=lambda x: x[0], reverse=True):
                    c_lines.pop(li)

                # Insert new KV lines just before the closing ---
                for il in insert_lines:
                    c_lines.insert(close_idx, il)

                clean_text = "\n".join(c_lines)
                content_changed = True

    # ── 4d. Normalise cover image key and fix path in frontmatter ────────
    if clean_text.startswith(FRONTMATTER_BOUNDARY):
        normalized_d = clean_text.replace("\r\n", "\n")
        d_lines = normalized_d.split("\n")
        close_idx_d = None
        for idx, line in enumerate(d_lines[1:], start=1):
            if line.strip() == FRONTMATTER_BOUNDARY:
                close_idx_d = idx
                break
        if close_idx_d is not None:
            for j in range(1, close_idx_d):
                line_lower = d_lines[j].strip().lower()
                for variant in ["cover_image:", "cover image:", "coverimage:", "cover-image:"]:
                    if line_lower.startswith(variant):
                        colon_pos = d_lines[j].index(":")
                        old_key = d_lines[j][:colon_pos].strip()
                        raw_val = d_lines[j][colon_pos + 1:].strip().strip('"').strip("'")
                        new_val = raw_val
                        # Fix the path if it's relative and broken
                        if raw_val and not raw_val.startswith(("http://", "https://")):
                            decoded = unquote(raw_val)
                            resolved = (index_path.parent / decoded).resolve()
                            if not resolved.exists():
                                filename = Path(decoded).name
                                found = _find_file_by_name(filename, article_root)
                                if found:
                                    rel = os.path.relpath(found, index_path.parent).replace(os.sep, "/")
                                    actions.append(f"Fix cover image path: {decoded} -> {rel}")
                                    new_val = rel
                                else:
                                    errors.append(f"Cover image not found: {decoded}")
                        if old_key != "cover_image":
                            actions.append(f"Normalise cover image key: {old_key} -> cover_image")
                        d_lines[j] = f"cover_image: {new_val}"
                        clean_text = "\n".join(d_lines)
                        content_changed = True
                        break

    # ── 5. Fix broken media paths ────────────────────────────────────────
    rewritten, media_fixes, media_missing = _fix_media_paths_in_markdown(
        clean_text,
        markdown_path=index_path,
        article_root=article_root,
    )
    if media_fixes:
        for fix in media_fixes:
            actions.append(f"Fix media path: {fix}")
        clean_text = rewritten
        content_changed = True

    for m in media_missing:
        errors.append(f"Media file not found: {m}")

    # ── 6. Validate remaining media after fixes ──────────────────────────
    remaining_refs = collect_media_references(clean_text, markdown_path=index_path)
    for raw_target, resolved in remaining_refs:
        if not resolved.exists():
            # Don't double-report what's already in media_missing
            fname = Path(unquote(raw_target)).name
            already_reported = any(fname in m for m in media_missing)
            if not already_reported:
                errors.append(f"Media file not found after fixes: {raw_target}")

    # ── 7. Write changes ─────────────────────────────────────────────────
    if content_changed and not dry_run:
        index_path.write_text(clean_text, encoding="utf-8")

    return actions, warnings, errors


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Auto-fix articles for SYNC-ARTICLES.py")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be changed without actually writing"
    )
    args = parser.parse_args()

    print(f"\n{BOLD}{'=' * 60}{RESET}")
    if args.dry_run:
        print(f"{BOLD}  Article Auto-Fix (DRY RUN — no changes written){RESET}")
    else:
        print(f"{BOLD}  Article Auto-Fix{RESET}")
    print(f"{BOLD}{'=' * 60}{RESET}\n")

    articles = discover_articles(REPO_ROOT)

    if not articles:
        print(f"{YELLOW}No articles found.{RESET}\n")
        return 0

    total_actions = 0
    total_warnings = 0
    total_errors = 0

    for article in articles:
        label = article["folder_name"] or article["path"].name
        layout_tag = "dir " if article["layout"] == "directory" else "file"

        article_actions, article_warnings, article_errors = fix_article(
            article, dry_run=args.dry_run
        )

        total_actions += len(article_actions)
        total_warnings += len(article_warnings)
        total_errors += len(article_errors)

        if not article_actions and not article_warnings and not article_errors:
            print(f"  {GREEN} OK {RESET}  [{layout_tag}] {BOLD}{label}{RESET}")
            continue

        has_errors = bool(article_errors)
        status = f"{RED}ERR{RESET}" if has_errors else f"{GREEN}FIX{RESET}"
        print(f"  {status}   [{layout_tag}] {BOLD}{label}{RESET}")

        for action in article_actions:
            verb = "Would" if args.dry_run else "Done"
            print(f"        {GREEN}✓{RESET} {verb}: {action}")

        for warning in article_warnings:
            print(f"        {YELLOW}!{RESET} Manual action needed: {warning}")

        for error in article_errors:
            print(f"        {RED}✗{RESET} {error}")

    # ── Summary ──────────────────────────────────────────────────────────
    print(f"\n{BOLD}{'─' * 60}{RESET}")
    parts = []
    if total_actions:
        verb = "to apply" if args.dry_run else "applied"
        parts.append(f"{GREEN}{total_actions} fix(es) {verb}{RESET}")
    if total_warnings:
        parts.append(f"{YELLOW}{total_warnings} manual action(s) needed{RESET}")
    if total_errors:
        parts.append(f"{RED}{total_errors} error(s) require attention{RESET}")

    if parts:
        print(f"  {' | '.join(parts)}")
    else:
        print(f"  {GREEN}{BOLD}All articles are already correct{RESET}")

    if args.dry_run and total_actions:
        print(f"\n  Run {CYAN}python3 fix-articles.py{RESET} (without --dry-run) to apply fixes")

    if total_warnings:
        print(f"\n  After fixing, run {CYAN}python3 validate-articles.py{RESET} to re-check")

    print()
    return 1 if total_errors else 0


if __name__ == "__main__":
    sys.exit(main())
