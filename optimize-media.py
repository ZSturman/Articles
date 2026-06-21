#!/usr/bin/env python3
"""
Optimize media files in article directories before pushing to GitHub.

Handles:
- Converting .mov/.avi/.webm video files to .mp4 (H.264 + AAC) via ffmpeg
- Compressing large images (PNG/JPEG) via Pillow
- Updating all markdown references to point to the new filenames
- Warning about files that still exceed GitHub's display/storage limits
- Blocking push if any single file exceeds the hard size limit

Thresholds:
- Images: compressed if > 500 KB
- Videos: converted to .mp4 if not already .mp4, re-encoded if > 10 MB
- WARN at > 10 MB per file (GitHub won't render large files inline)
- BLOCK at > 50 MB per file (GitHub warns; 100 MB is the hard rejection)

Usage:
  python3 optimize-media.py            # optimize and update references
  python3 optimize-media.py --dry-run  # preview what would change
  python3 optimize-media.py --check    # only check sizes, block if too large
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import unquote, quote

# ── Constants ────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).parent

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
VIDEO_CONVERT_EXTS = {".mov", ".avi", ".webm"}  # will be converted to .mp4
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".webm"}
ALL_MEDIA_EXTS = IMAGE_EXTS | VIDEO_EXTS | {".gif", ".svg", ".ico", ".pdf"}

# Size thresholds in bytes
IMAGE_COMPRESS_THRESHOLD = 500 * 1024       # 500 KB
VIDEO_REENCODE_THRESHOLD = 10 * 1024 * 1024  # 10 MB
WARN_SIZE = 10 * 1024 * 1024                 # 10 MB — GitHub won't render inline
BLOCK_SIZE = 50 * 1024 * 1024                # 50 MB — GitHub warns, near hard limit

MARKDOWN_FILE_EXTS = {".md", ".markdown"}

IGNORED_NAMES = {
    ".git", ".github", ".venv", "__pycache__", "node_modules",
    "publish", "public", "build", "dist",
}
IGNORED_FILES = {
    "README.md", "readme.md", "CHANGELOG.md", "LICENSE.md",
    "SYNC-ARTICLES.py", "validate-articles.py", "fix-articles.py",
    "optimize-media.py", "requirements.txt", ".gitignore", ".env",
    ".publish-state.json",
}

# Regexes for finding media references in markdown
MARKDOWN_LINK_RE = re.compile(
    r"(?P<prefix>!?\[[^\]]*\]\()(?P<target>[^)\n]+)(?P<suffix>\))"
)
HTML_ATTR_RE = re.compile(
    r'(?P<attr>\b(?:src|href)=)(?P<quote>["\'])(?P<target>[^"\']+)(?P=quote)'
)

# ── Colours ──────────────────────────────────────────────────────────────────

RESET = "\033[0m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BOLD = "\033[1m"
CYAN = "\033[36m"
DIM = "\033[2m"

# ── Helpers ──────────────────────────────────────────────────────────────────

def human_size(size_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if abs(size_bytes) < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def has_pillow() -> bool:
    try:
        from PIL import Image
        return True
    except ImportError:
        return False


# ── Discovery ────────────────────────────────────────────────────────────────

def discover_article_dirs(repo_root: Path) -> List[Path]:
    """Find all article directories (same logic as validate-articles.py)."""
    dirs: List[Path] = []
    search_roots = []
    articles_dir = repo_root / "articles"
    if articles_dir.exists() and articles_dir.is_dir():
        search_roots.append(articles_dir)
    search_roots.append(repo_root)

    for search_root in search_roots:
        if not search_root.exists():
            continue
        for entry in sorted(search_root.iterdir(), key=lambda p: p.name.lower()):
            if not entry.is_dir():
                continue
            if entry.name.startswith("."):
                continue
            if entry.name.lower() in {n.lower() for n in IGNORED_NAMES}:
                continue
            dirs.append(entry)
    return dirs


def find_media_files(directory: Path) -> List[Path]:
    """Recursively find all media files in a directory."""
    media_files = []
    for root, _dirs, files in os.walk(directory):
        root_path = Path(root)
        for f in files:
            fpath = root_path / f
            if fpath.suffix.lower() in ALL_MEDIA_EXTS:
                media_files.append(fpath)
    return media_files


def find_markdown_files(directory: Path) -> List[Path]:
    """Recursively find all markdown files in a directory."""
    md_files = []
    for root, _dirs, files in os.walk(directory):
        root_path = Path(root)
        for f in files:
            fpath = root_path / f
            if fpath.suffix.lower() in MARKDOWN_FILE_EXTS:
                md_files.append(fpath)
    return md_files


# ── Video Optimization ───────────────────────────────────────────────────────

def convert_video_to_mp4(src: Path, dry_run: bool = False) -> Optional[Path]:
    """
    Convert a video file to .mp4 (H.264 + AAC).
    Returns the new path, or None if conversion failed or was skipped.
    """
    if not has_ffmpeg():
        print(f"    {YELLOW}SKIP{RESET} ffmpeg not installed — cannot convert {src.name}")
        return None

    dst = src.with_suffix(".mp4")

    # If source is already .mp4, re-encode only if it's too large
    if src.suffix.lower() == ".mp4":
        if src.stat().st_size <= VIDEO_REENCODE_THRESHOLD:
            return None  # already fine
        # Re-encode in place to a temp then replace
        dst = src.with_name(src.stem + "_optimized.mp4")

    if dry_run:
        print(f"    {CYAN}WOULD{RESET} convert {src.name} → {dst.name}")
        return dst

    print(f"    {CYAN}CONVERTING{RESET} {src.name} → {dst.name} ...", end=" ", flush=True)

    try:
        cmd = [
            "ffmpeg", "-y", "-i", str(src),
            "-c:v", "libx264",
            "-preset", "slow",
            "-crf", "28",
            "-c:a", "aac",
            "-b:a", "128k",
            "-movflags", "+faststart",
            "-pix_fmt", "yuv420p",
            str(dst),
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            print(f"{RED}FAILED{RESET}")
            print(f"      ffmpeg stderr: {result.stderr[:500]}")
            if dst.exists():
                dst.unlink()
            return None
    except subprocess.TimeoutExpired:
        print(f"{RED}TIMEOUT{RESET}")
        if dst.exists():
            dst.unlink()
        return None

    old_size = src.stat().st_size
    new_size = dst.stat().st_size

    print(f"{GREEN}OK{RESET} ({human_size(old_size)} → {human_size(new_size)})")

    # If re-encoding an existing .mp4, replace the original
    if src.suffix.lower() == ".mp4":
        src.unlink()
        dst.rename(src)
        return src

    return dst


# ── Image Optimization ───────────────────────────────────────────────────────

def optimize_image(src: Path, dry_run: bool = False) -> bool:
    """
    Compress an image if it exceeds the threshold.
    Returns True if the image was modified.
    """
    if not has_pillow():
        print(f"    {YELLOW}SKIP{RESET} Pillow not installed — cannot compress {src.name}")
        return False

    size = src.stat().st_size
    if size <= IMAGE_COMPRESS_THRESHOLD:
        return False

    from PIL import Image

    ext = src.suffix.lower()

    if dry_run:
        print(f"    {CYAN}WOULD{RESET} compress {src.name} ({human_size(size)})")
        return False

    print(f"    {CYAN}COMPRESSING{RESET} {src.name} ({human_size(size)}) ...", end=" ", flush=True)

    try:
        img = Image.open(src)

        # Convert RGBA PNGs to RGB JPEG if very large (> 2MB), else optimize PNG
        if ext == ".png":
            # Try optimized PNG first
            tmp = src.with_name(src.stem + "_opt.png")
            img.save(tmp, "PNG", optimize=True)
            new_size = tmp.stat().st_size
            if new_size < size:
                tmp.rename(src)
                print(f"{GREEN}OK{RESET} ({human_size(size)} → {human_size(new_size)})")
                return True
            else:
                tmp.unlink()
                print(f"{DIM}already optimal{RESET}")
                return False
        elif ext in {".jpg", ".jpeg"}:
            tmp = src.with_name(src.stem + "_opt" + ext)
            img.save(tmp, "JPEG", quality=80, optimize=True)
            new_size = tmp.stat().st_size
            if new_size < size:
                tmp.rename(src)
                print(f"{GREEN}OK{RESET} ({human_size(size)} → {human_size(new_size)})")
                return True
            else:
                tmp.unlink()
                print(f"{DIM}already optimal{RESET}")
                return False
        elif ext == ".webp":
            tmp = src.with_name(src.stem + "_opt.webp")
            img.save(tmp, "WEBP", quality=75, method=6)
            new_size = tmp.stat().st_size
            if new_size < size:
                tmp.rename(src)
                print(f"{GREEN}OK{RESET} ({human_size(size)} → {human_size(new_size)})")
                return True
            else:
                tmp.unlink()
                print(f"{DIM}already optimal{RESET}")
                return False
        else:
            print(f"{DIM}unsupported format{RESET}")
            return False
    except Exception as exc:
        print(f"{RED}ERROR{RESET} {exc}")
        return False


# ── Markdown Reference Updates ───────────────────────────────────────────────

def update_markdown_references(
    md_file: Path,
    rename_map: Dict[str, str],
    dry_run: bool = False,
) -> bool:
    """
    Update media references in a markdown file based on rename_map.
    rename_map: {old_filename: new_filename} (just filenames, not full paths)
    Returns True if the file was modified.
    """
    if not rename_map:
        return False

    text = md_file.read_text(encoding="utf-8")
    original = text

    for old_name, new_name in rename_map.items():
        # Handle both URL-encoded and plain references
        old_variants = {old_name, quote(old_name, safe="/"), unquote(old_name)}
        new_plain = new_name

        for old_ref in old_variants:
            # Replace in markdown links: ![alt](path/old_name)
            # We need to match the filename at the end of any relative path
            pattern = re.compile(
                r"(?P<before>!?\[[^\]]*\]\([^)]*?)"
                + re.escape(old_ref)
                + r"(?P<after>\))"
            )
            text = pattern.sub(
                lambda m: m.group("before") + new_plain + m.group("after"),
                text,
            )

            # Replace in HTML attributes: src="path/old_name"
            pattern_html = re.compile(
                r'(?P<before>(?:src|href)=["\'][^"\']*?)'
                + re.escape(old_ref)
                + r"(?P<after>[\"'])"
            )
            text = pattern_html.sub(
                lambda m: m.group("before") + new_plain + m.group("after"),
                text,
            )

    if text != original:
        if dry_run:
            for old_name, new_name in rename_map.items():
                if old_name in original or quote(old_name, safe="/") in original:
                    print(f"    {CYAN}WOULD UPDATE{RESET} {md_file.name}: {old_name} → {new_name}")
            return False
        md_file.write_text(text, encoding="utf-8")
        for old_name, new_name in rename_map.items():
            if old_name != new_name:
                print(f"    {GREEN}UPDATED{RESET} {md_file.name}: {old_name} → {new_name}")
        return True

    return False


# ── Size Check ───────────────────────────────────────────────────────────────

def check_media_sizes(repo_root: Path) -> Tuple[List[str], List[str]]:
    """
    Scan all media files and return (warnings, blockers).
    warnings: files > WARN_SIZE
    blockers: files > BLOCK_SIZE
    """
    warnings: List[str] = []
    blockers: List[str] = []

    dirs = discover_article_dirs(repo_root)
    for d in dirs:
        for media in find_media_files(d):
            size = media.stat().st_size
            rel = media.relative_to(repo_root)
            if size > BLOCK_SIZE:
                blockers.append(
                    f"{rel} ({human_size(size)}) exceeds {human_size(BLOCK_SIZE)} — "
                    f"must be reduced or removed"
                )
            elif size > WARN_SIZE:
                warnings.append(
                    f"{rel} ({human_size(size)}) exceeds {human_size(WARN_SIZE)} — "
                    f"GitHub may not render this inline"
                )

    return warnings, blockers


# ── Main Logic ───────────────────────────────────────────────────────────────

def optimize_directory(article_dir: Path, dry_run: bool = False) -> Dict[str, str]:
    """
    Optimize all media in an article directory.
    Returns a rename map: {old_filename: new_filename} for files that changed names.
    """
    rename_map: Dict[str, str] = {}
    media_files = find_media_files(article_dir)

    for media in media_files:
        ext = media.suffix.lower()

        # Convert non-mp4 videos to mp4
        if ext in VIDEO_CONVERT_EXTS:
            new_path = convert_video_to_mp4(media, dry_run=dry_run)
            if new_path and new_path != media:
                rename_map[media.name] = new_path.name
                if not dry_run:
                    # Remove original after successful conversion
                    media.unlink()
                    print(f"    {GREEN}REMOVED{RESET} original {media.name}")

        # Re-encode oversized mp4
        elif ext == ".mp4":
            convert_video_to_mp4(media, dry_run=dry_run)

        # Compress large images
        elif ext in IMAGE_EXTS:
            optimize_image(media, dry_run=dry_run)

    return rename_map


def main() -> int:
    parser = argparse.ArgumentParser(description="Optimize media files for GitHub")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without applying them")
    parser.add_argument("--check", action="store_true", help="Only check sizes, report and exit")
    args = parser.parse_args()

    repo_root = REPO_ROOT

    print(f"\n{BOLD}{'=' * 60}{RESET}")
    print(f"{BOLD}  Media Optimization{RESET}")
    print(f"{BOLD}{'=' * 60}{RESET}\n")

    # ── Check mode: just validate sizes ──────────────────────────────────
    if args.check:
        warnings, blockers = check_media_sizes(repo_root)

        if warnings:
            print(f"  {YELLOW}{BOLD}Warnings:{RESET}")
            for w in warnings:
                print(f"    {YELLOW}!{RESET} {w}")
            print()

        if blockers:
            print(f"  {RED}{BOLD}Blockers:{RESET}")
            for b in blockers:
                print(f"    {RED}✗{RESET} {b}")
            print()
            print(f"{BOLD}{'─' * 60}{RESET}")
            print(f"{RED}{BOLD}  PUSH BLOCKED — {len(blockers)} file(s) too large{RESET}")
            print(f"{BOLD}{'─' * 60}{RESET}")
            print()
            print(f"  {CYAN}Run:{RESET}  python3 optimize-media.py")
            print(f"  {CYAN}  or:{RESET}  python3 optimize-media.py --dry-run")
            print()
            return 1

        if not warnings:
            print(f"  {GREEN}{BOLD}All media files are within size limits.{RESET}\n")

        return 0

    # ── Optimization mode ────────────────────────────────────────────────
    if not has_ffmpeg():
        print(f"  {YELLOW}WARNING:{RESET} ffmpeg not found — video conversion will be skipped")
        print(f"  {CYAN}Install:{RESET} brew install ffmpeg\n")

    if not has_pillow():
        print(f"  {YELLOW}WARNING:{RESET} Pillow not found — image compression will be skipped")
        print(f"  {CYAN}Install:{RESET} pip install Pillow\n")

    dirs = discover_article_dirs(repo_root)

    if not dirs:
        print(f"  {YELLOW}No article directories found.{RESET}\n")
        return 0

    total_renames = 0
    total_optimized = 0

    for article_dir in dirs:
        media_files = find_media_files(article_dir)
        if not media_files:
            continue

        rel_dir = article_dir.relative_to(repo_root)
        print(f"  {BOLD}{rel_dir}/{RESET}")

        # Optimize media and collect renames
        rename_map = optimize_directory(article_dir, dry_run=args.dry_run)
        total_renames += len(rename_map)

        # Update markdown references for any renamed files
        if rename_map:
            md_files = find_markdown_files(article_dir)
            for md_file in md_files:
                updated = update_markdown_references(md_file, rename_map, dry_run=args.dry_run)
                if updated:
                    total_optimized += 1

        print()

    # ── Post-optimization size check ─────────────────────────────────────
    if not args.dry_run:
        print(f"{BOLD}{'─' * 60}{RESET}")
        print(f"{BOLD}  Post-optimization size check{RESET}")
        print(f"{BOLD}{'─' * 60}{RESET}\n")

        warnings, blockers = check_media_sizes(repo_root)

        if warnings:
            print(f"  {YELLOW}{BOLD}Warnings (may not render on GitHub):{RESET}")
            for w in warnings:
                print(f"    {YELLOW}!{RESET} {w}")
            print()

        if blockers:
            print(f"  {RED}{BOLD}Blockers (will cause push issues):{RESET}")
            for b in blockers:
                print(f"    {RED}✗{RESET} {b}")
            print()
            print(f"  {CYAN}These files need manual intervention:{RESET}")
            print(f"    - Trim the video to a shorter clip")
            print(f"    - Reduce resolution or increase compression")
            print(f"    - Host externally and link to it instead")
            print()
            return 1

        if not warnings:
            print(f"  {GREEN}{BOLD}All media files are within size limits.{RESET}\n")
    else:
        print(f"  {CYAN}Dry run complete — no files were changed.{RESET}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
