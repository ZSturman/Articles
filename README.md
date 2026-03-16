# Articles

Source of truth for articles published to [zachary-sturman.com](https://zachary-sturman.com), [DEV.to](https://dev.to), [Hashnode](https://hashnode.com), and [Medium](https://medium.com).

## Repository Structure

```
<slug>/
  index.md          # Article content (Markdown with optional frontmatter)
  images/           # Optional local images/assets
```

Each article lives in its own folder. The folder name is the slug.

---

## Publishing Workflow

A lightweight Python tool that discovers articles from this repo and cross-posts them to DEV.to, Hashnode, and Medium. Your personal site is the canonical source — all syndicated copies point back to `https://zachary-sturman.com/articles/<slug>`.

### How It Works

1. **Discovery** — Scans the repo root for folders containing `index.md`. Each folder is one article.
2. **Frontmatter parsing** — Reads YAML frontmatter for metadata (title, tags, summary, etc.). Unknown keys are ignored. All fields are optional.
3. **Content transform** — Rewrites relative image paths to GitHub raw URLs, strips the leading H1 (platforms render their own), and adjusts tags per platform constraints.
4. **Canonical URL** — If `canonical_url` is in frontmatter, it's used as-is. Otherwise, it's auto-derived as `https://zachary-sturman.com/articles/<slug>`.
5. **State tracking** — `.publish-state.json` records content hashes and platform IDs/URLs. This prevents duplicate posts and enables updates.
6. **Publish** — Creates or updates posts on each configured platform. If content hasn't changed since last publish, the article is skipped (use `--force` to override).

### Frontmatter (all optional)

```yaml
---
title: My Article Title        # Fallback: first H1 in body, then slug
summary: A short description   # Used as subtitle/description on platforms
tags:
  - python
  - systems
canonical_url: https://...     # Override the auto-derived canonical URL
cover_image: images/cover.jpg  # Relative path to cover image
series: My Series Name         # DEV.to series (ignored elsewhere)
---
```

Any other frontmatter keys (e.g., `publishedAt`, `updatedAt`, project IDs) are silently ignored.

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Set API keys

Export the tokens for the platforms you want to publish to. You only need the ones you use.

```bash
# DEV.to — get your key at https://dev.to/settings/extensions
export DEVTO_API_KEY="your-devto-api-key"

# Hashnode — get your token at https://hashnode.com/settings/developer
export HASHNODE_TOKEN="your-hashnode-token"
# Find your publication ID in your Hashnode dashboard URL or via their API
export HASHNODE_PUBLICATION_ID="your-publication-id"

# Medium (deprecated API — creates drafts only)
# Get a token at https://medium.com/me/settings/security
export MEDIUM_TOKEN="your-medium-token"
```

A platform is active only if its key is set. Missing keys simply skip that platform.

### 3. For GitHub Actions

Add these as [repository secrets](https://docs.github.com/en/actions/security-for-github-actions/security-guides/using-secrets-in-github-actions) in your repo settings:

- `DEVTO_API_KEY`
- `HASHNODE_TOKEN`
- `HASHNODE_PUBLICATION_ID`
- `MEDIUM_TOKEN`

---

## Usage

### Publish one article

```bash
python -m publish designing-a-notion-linear-sync-engine-that-could-actually-be-trusted
```

### Publish all eligible articles

```bash
python -m publish --all
```

### Dry run (see what would happen)

```bash
python -m publish --all --dry-run
```

### Preview transformed markdown

```bash
python -m publish my-article --preview
```

### Target specific platforms

```bash
python -m publish my-article --platform devto,hashnode
```

### Force re-publish (even if unchanged)

```bash
python -m publish my-article --force
```

### Verbose logging

```bash
python -m publish --all -v
```

### Via GitHub Actions

Go to **Actions → Publish Articles → Run workflow** and fill in:
- **slug**: article folder name, or `all`
- **dry_run**: check to preview without publishing
- **platforms**: `devto`, `hashnode`, `medium`, or `all`
- **force**: check to re-publish unchanged articles

---

## Publish State

Publishing state is tracked in `.publish-state.json` at the repo root. This file is committed to git.

```json
{
  "my-article-slug": {
    "content_hash": "sha256-of-index-md",
    "devto": {
      "id": "123456",
      "url": "https://dev.to/zsturman/my-article-slug",
      "published_at": "2026-03-16T12:00:00+00:00"
    },
    "hashnode": {
      "id": "abc123",
      "url": "https://hashnode.com/post/my-article-slug",
      "published_at": "2026-03-16T12:00:00+00:00"
    }
  }
}
```

- **Content hash** is a SHA-256 of the full `index.md` file (including frontmatter). Any change to the file triggers an update on the next publish run.
- The state file is auto-committed by the GitHub Actions workflow after each publish.
- To re-publish an article from scratch, delete its entry from the state file.

---

## Image Handling

Relative image paths in `index.md` (like `![alt](images/photo.jpg)` or Notion-export-style paths) are rewritten to GitHub raw URLs:

```
https://raw.githubusercontent.com/ZSturman/Articles/main/<slug>/images/photo.jpg
```

**Requirement**: The repo must be **public** for images to resolve on publishing platforms. If the repo is private, host images externally and use absolute URLs in your markdown, or use a service like [imgur](https://imgur.com) / [Cloudinary](https://cloudinary.com).

---

## Platform Notes

| Feature | DEV.to | Hashnode | Medium |
|---|---|---|---|
| **API status** | Active | Active (GraphQL) | ⚠️ Deprecated |
| **Create posts** | ✅ | ✅ | ✅ (draft only) |
| **Update posts** | ✅ | ✅ | ❌ |
| **Canonical URL field** | `canonical_url` | `originalArticleURL` | `canonicalUrl` |
| **Tag limits** | 4 tags, lowercase, alphanumeric | Resolved via API search | 5 tags, 25 chars |
| **Cover image** | `main_image` (URL) | `coverImageOptions` (URL) | Not supported via API |
| **Series** | ✅ | Ignored | Ignored |

### Medium limitations

- The Medium API is **officially deprecated** (archived March 2023). Existing tokens may still work.
- Posts are created as **drafts** by default. You'll need to manually publish them from your Medium dashboard.
- **No update support** — if you change an article after the initial publish, the tool will warn you but cannot push the update. Edit manually on medium.com.
- If Medium publishing fails, the other platforms are not affected.

### Hashnode tag resolution

Hashnode requires tag IDs, not plain strings. The tool searches for each tag by name via the Hashnode API and uses the closest match. If a tag isn't found, it's skipped with a warning.

---

## Error Handling

- **Retries**: All platform clients retry on HTTP 429 (rate limited) and 5xx (server errors) with exponential backoff, up to 3 attempts.
- **Partial failure**: If one platform fails, the others still proceed. The exit code is non-zero if any errors occurred.
- **Rate limiting**: A 2-second delay is added between articles when publishing with `--all`.
- **Safe re-runs**: Thanks to content hashing in the state file, re-running the publish command is always safe — unchanged articles are skipped.
