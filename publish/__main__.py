"""CLI entry point: python -m publish"""

import argparse
import logging
import sys
import time
from pathlib import Path

from . import config
from .discover import Article, discover_articles
from .platforms import PublishResult, get_platform_registry
from .state import PublishState
from .transform import cover_image_url, tags_for_platform, transform_for_platform

logger = logging.getLogger("publish")


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(levelname)-8s %(message)s",
        handlers=[logging.StreamHandler()],
    )


def find_repo_root() -> Path:
    """Walk up from CWD to find the repo root (contains .git or .publish-state.json)."""
    candidate = Path.cwd()
    for _ in range(10):
        if (candidate / ".git").exists() or (candidate / ".publish-state.json").exists():
            return candidate
        parent = candidate.parent
        if parent == candidate:
            break
        candidate = parent
    # Fallback: assume CWD is root
    return Path.cwd()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="publish",
        description="Publish articles from this repo to DEV.to, Hashnode, and Medium.",
    )
    parser.add_argument(
        "slug",
        nargs="?",
        default=None,
        help="Slug of a specific article to publish (folder name).",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        dest="publish_all",
        help="Publish all discovered articles.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would happen without making API calls.",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Print the transformed markdown for each platform to stdout.",
    )
    parser.add_argument(
        "--platform",
        type=str,
        default=None,
        help="Comma-separated list of platforms to target (devto,hashnode,medium).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-publish even if content hash hasn't changed.",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging.",
    )
    return parser


def resolve_platforms(platform_arg: str | None) -> list[str]:
    """Determine which platforms to target based on CLI arg and configured keys."""
    active = config.active_platforms()
    if not platform_arg or platform_arg == "all":
        return active
    requested = [p.strip().lower() for p in platform_arg.split(",")]
    selected = [p for p in requested if p in active]
    skipped = [p for p in requested if p not in active]
    for p in skipped:
        if p in ("devto", "hashnode", "medium"):
            logger.warning("Platform '%s' requested but no API key configured — skipping", p)
        else:
            logger.warning("Unknown platform '%s' — skipping", p)
    return selected


def handle_preview(articles: list[Article], platforms: list[str]):
    """Print transformed markdown for inspection."""
    for article in articles:
        for platform in platforms:
            body = transform_for_platform(article, platform)
            tags = tags_for_platform(article, platform)
            cover = cover_image_url(article)
            ready = article.is_ready_to_post
            print(f"\n{'='*72}")
            print(f"  Article:   {article.slug}")
            print(f"  Status:    {article.status}{'  ✓ will publish' if ready else '  ✗ skipped (not ready)'}")
            print(f"  Platform:  {platform}")
            print(f"  Title:     {article.title}")
            print(f"  Canonical: {article.canonical_url}")
            print(f"  Tags:      {', '.join(tags) if tags else '(none)'}")
            print(f"  Cover:     {cover or '(none)'}")
            print(f"  Summary:   {article.summary[:80] or '(none)'}")
            print(f"{'='*72}")
            print(body)
            print()


def handle_dry_run(articles: list[Article], platforms: list[str], state: PublishState):
    """Show what would happen without making API calls."""
    for article in articles:
        content_hash = state.content_hash(article.index_path)
        ready = article.is_ready_to_post
        print(f"\n--- {article.slug} ---")
        print(f"  Title:     {article.title}")
        print(f"  Status:    {article.status}{'  ✓ will publish' if ready else '  ✗ skipped (not ready)'}")
        print(f"  Canonical: {article.canonical_url}")
        print(f"  Hash:      {content_hash[:12]}...")

        if not ready:
            print(f"  [all platforms] Skipped — set frontmatter status to 'ready to post' to enable publishing")
            continue

        for platform in platforms:
            published = state.is_published(article.slug, platform)
            changed = state.needs_update(article.slug, content_hash)
            tags = tags_for_platform(article, platform)

            if not published:
                print(f"  [{platform}] Would CREATE new post (tags: {', '.join(tags) or 'none'})")
            elif changed:
                existing_id = state.get_platform_id(article.slug, platform)
                registry = get_platform_registry()
                client_cls = registry.get(platform)
                if client_cls and not client_cls().supports_update:
                    print(f"  [{platform}] Content changed but platform does not support updates (id: {existing_id})")
                else:
                    print(f"  [{platform}] Would UPDATE existing post (id: {existing_id})")
            else:
                print(f"  [{platform}] Already published, no changes")


def publish_article(
    article: Article,
    platforms: list[str],
    state: PublishState,
    force: bool = False,
    dry_run: bool = False,
) -> list[str]:
    """Publish or update one article across platforms. Returns list of errors."""
    if not article.is_ready_to_post:
        logger.info("%s — status is '%s', skipping platform publish", article.slug, article.status)
        return []

    errors = []
    content_hash = state.content_hash(article.index_path)
    registry = get_platform_registry()

    for platform in platforms:
        published = state.is_published(article.slug, platform)
        changed = state.needs_update(article.slug, content_hash)

        if published and not changed and not force:
            logger.info("[%s] %s — already published, no changes", platform, article.slug)
            continue

        body = transform_for_platform(article, platform)
        tags = tags_for_platform(article, platform)
        cover = cover_image_url(article)

        client_cls = registry.get(platform)
        if not client_cls:
            logger.error("Unknown platform: %s", platform)
            errors.append(f"{platform}: unknown platform")
            continue

        client = client_cls()

        try:
            if published and (changed or force):
                existing_id = state.get_platform_id(article.slug, platform)
                if not client.supports_update:
                    logger.warning(
                        "[%s] %s — content changed but platform does not support updates (id: %s)",
                        platform, article.slug, existing_id,
                    )
                    continue
                logger.info("[%s] %s — updating (id: %s)...", platform, article.slug, existing_id)
                result = client.update(article, body, tags, cover, existing_id)
                logger.info("[%s] %s — updated: %s", platform, article.slug, result.url)
            else:
                logger.info("[%s] %s — creating...", platform, article.slug)
                result = client.publish(article, body, tags, cover)
                logger.info("[%s] %s — published: %s", platform, article.slug, result.url)

            state.record_publish(article.slug, platform, result.post_id, result.url, content_hash)

        except NotImplementedError as e:
            logger.warning("[%s] %s — %s", platform, article.slug, e)
        except Exception as e:
            logger.error("[%s] %s — failed: %s", platform, article.slug, e)
            errors.append(f"{platform}: {e}")

    return errors


def main():
    parser = build_parser()
    args = parser.parse_args()
    setup_logging(args.verbose)

    if not args.slug and not args.publish_all:
        parser.error("Provide a slug or use --all")

    repo_root = find_repo_root()
    logger.debug("Repo root: %s", repo_root)

    # Discover articles
    slugs = [args.slug] if args.slug else None
    articles = discover_articles(repo_root, slugs)

    if not articles:
        if args.slug:
            logger.error("Article not found: %s", args.slug)
        else:
            logger.info("No articles found")
        sys.exit(1)

    logger.info("Discovered %d article(s): %s", len(articles), ", ".join(a.slug for a in articles))

    ready = [a for a in articles if a.is_ready_to_post]
    not_ready = [a for a in articles if not a.is_ready_to_post]
    if not_ready:
        logger.info(
            "Skipping %d article(s) not marked 'ready to post': %s",
            len(not_ready), ", ".join(a.slug for a in not_ready),
        )
    if ready:
        logger.info("Ready to publish: %s", ", ".join(a.slug for a in ready))

    # Resolve platforms
    platforms = resolve_platforms(args.platform)
    if not platforms:
        logger.error("No platforms configured. Set at least one API key (DEVTO_API_KEY, HASHNODE_TOKEN, MEDIUM_TOKEN).")
        sys.exit(1)

    logger.info("Target platforms: %s", ", ".join(platforms))

    # Preview mode
    if args.preview:
        handle_preview(articles, platforms)
        return

    # Dry run mode
    state = PublishState(repo_root)

    if args.dry_run:
        handle_dry_run(articles, platforms, state)
        return

    # Publish
    all_errors = []
    for i, article in enumerate(articles):
        if i > 0:
            time.sleep(2)  # Small delay between articles to respect rate limits
        errors = publish_article(article, platforms, state, force=args.force)
        all_errors.extend(errors)

    # Save state
    state.save()
    logger.info("State saved to %s", state.path)

    # Summary
    if all_errors:
        logger.error("Completed with %d error(s):", len(all_errors))
        for err in all_errors:
            logger.error("  - %s", err)
        sys.exit(1)
    else:
        logger.info("Done — all operations succeeded.")


if __name__ == "__main__":
    main()
