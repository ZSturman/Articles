"""Configuration loaded from environment variables."""

import os
from pathlib import Path


def _find_dotenv() -> Path | None:
    for candidate in (Path.cwd(), *Path.cwd().parents):
        env_path = candidate / ".env"
        if env_path.is_file():
            return env_path
    return None


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"\"", "'"}:
        return value[1:-1]
    return value


def _load_dotenv() -> None:
    env_path = _find_dotenv()
    if not env_path:
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue

        os.environ[key] = _strip_quotes(value.strip())


_load_dotenv()

CANONICAL_BASE_URL = os.environ.get("CANONICAL_BASE_URL", "https://zachary-sturman.com/articles")

GITHUB_REPOSITORY = os.environ.get("GITHUB_REPOSITORY", "ZSturman/Articles")
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "main")

DEVTO_API_KEY = os.environ.get("DEVTO_API_KEY", "")
HASHNODE_TOKEN = os.environ.get("HASHNODE_TOKEN", "")
HASHNODE_PUBLICATION_ID = os.environ.get("HASHNODE_PUBLICATION_ID", "")
MEDIUM_TOKEN = os.environ.get("MEDIUM_TOKEN", "")


def active_platforms() -> list[str]:
    """Return list of platform names that have credentials configured."""
    platforms = []
    if DEVTO_API_KEY:
        platforms.append("devto")
    if HASHNODE_TOKEN and HASHNODE_PUBLICATION_ID:
        platforms.append("hashnode")
    if MEDIUM_TOKEN:
        platforms.append("medium")
    return platforms


def github_raw_base() -> str:
    """Base URL for raw file access on GitHub."""
    return f"https://raw.githubusercontent.com/{GITHUB_REPOSITORY}/{GITHUB_BRANCH}"
