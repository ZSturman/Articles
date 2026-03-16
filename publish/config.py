"""Configuration loaded from environment variables."""

import os

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
