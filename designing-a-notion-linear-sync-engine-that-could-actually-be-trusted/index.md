---
title: Designing a Notion–Linear Sync Engine That Could Actually Be Trusted
summary: A deep dive into the architecture and design decisions behind a bidirectional sync engine that keeps Notion and Linear in sync reliably over time.
publishedAt: 2026-03-16
updatedAt: 2026-03-16
tags:
  - systems
  - notion
---

# **Designing a Notion–Linear Sync Engine That Could Actually Be Trusted**

![Flask Written Notes.jpeg](Designing%20a%20Notion%E2%80%93Linear%20Sync%20Engine%20That%20Could%20A/Flask_Written_Notes.jpeg)

Notion and Linear overlap just enough to create a real problem.

Planning often starts in Notion because it is flexible and easy to shape around a team’s workflow. Execution often moves into Linear because it is structured, fast, and better at handling active delivery. That split works for a while, until the same projects, milestones, and tasks start living in both places and slowly drift out of sync.

I built a Python service to close that gap. At first, it seemed like a straightforward integration problem: fetch records from Notion, fetch records from Linear, compare them, and push updates where needed.

It turned out to be more involved than that.

Once I started dealing with conflicting edits, relationship preservation, duplicate prevention, retry logic, and sync history, the project stopped being a script and became a real synchronization engine. The interesting part was not the API wiring. It was the architecture needed to make the sync reliable enough to trust.

## **What This Service Actually Does**

At a high level, the service keeps three kinds of records in sync between Notion and Linear:

- Projects
- Milestones
- Tasks

The sync is bidirectional, which means changes can originate in either system. On each run, the service authenticates with both APIs, fetches records from each side, normalizes them into shared internal models, compares them to detect differences, and then applies creates, updates, deletes, or conflict decisions back to the opposite system.

It also preserves relationships between records, keeps local sync state, handles retries and rate limits, and exposes the whole flow through a CLI.

That last part matters because this is not meant to be a one-off import or export. It is meant to behave like an ongoing system.

## **Why This Problem Is Harder Than It Looks**

The surface mapping sounds simple enough.

A Notion project page roughly maps to a Linear project. A Notion milestone page roughly maps to a Linear milestone. A Notion task page roughly maps to a Linear issue.

But once you try to make those concepts move back and forth reliably, the mismatch shows up quickly.

Notion and Linear do not share the same schema. Their IDs are different. Their workflows and status models are different. Parent-child relationships have to survive sync. Both sides can change the same record before the next run. APIs can rate limit or fail. And if the system loses track of what it already created, duplicate records start appearing almost immediately.

So the real problem is not just moving data. It is building a system that can compare meaning across two different tools, decide what changed, and preserve structure while doing it.

That became the central design problem.

## **The Architectural Decision That Made It Work**

The design choice that made the whole project workable was introducing a shared internal model layer.

Instead of comparing raw Notion responses against raw Linear GraphQL nodes, the service translates both into unified Python models first. Projects become UnifiedProject, milestones become UnifiedMilestone, and tasks become UnifiedTask.

That means the sync engine does not spend its time reasoning about two external formats. It works against its own internal language.

Once records are normalized into that shared representation, the rest of the system gets much simpler. The reconciler can compare like with like. The conflict logic can operate on consistent fields. The mappers can translate platform-specific semantics at the edges, instead of scattering those rules throughout the codebase.

That one decision changed the project from an integration held together by conditionals into a system with a stable center.

```markdown
Notion API data + Linear API data
                ↓
        Unified internal models
                ↓
         Reconcile differences
                ↓
      Write changes to target side
                ↓
      Resolve relationships + save state
```

## **How the System Is Structured**

Once the internal model layer was in place, the rest of the architecture fell into a fairly clean shape.

**Configuration** handles environment variables, API credentials, database IDs, field mappings, and conflict strategy settings.

**API clients** are responsible for talking to Notion and Linear directly. They handle authentication, requests, pagination, rate limiting, and the details of each platform’s API shape.

**Unified models** represent the internal source of truth. This is the layer that lets the rest of the system think in terms of records instead of API payloads.

**Mappers** convert records into and out of those unified models. They also handle semantic translation, like mapping a Notion priority label to Linear’s numeric priority or converting a Linear workflow state into a Notion-friendly status.

**The reconciler** compares normalized records from both systems and decides whether each one should be created, updated, deleted, or treated as a conflict.

**The relation resolver** exists because records cannot always be fully connected in a single pass. It handles relationship repair after base entities have already been created and linked.

**The state store** keeps a local memory of what has already been synced, including linked IDs, timestamps, hashes, and prior sync history.

**Utilities** cover retries, logging, and operational support.

Put together, the architecture looks something like this:

```markdown
CLI
→ Config
→ API Clients
→ Unified Models
→ Mappers
→ Reconciler
→ Relation Resolver
→ State Store
→ Notion / Linear APIs
```

## **Following One Task Through the Pipeline**

The easiest way to explain the sync flow is to follow one task through it.

Imagine a user creates a task in Notion called **Write API docs**. They set the status to **In Progress**, the priority to **High**, check the sync box, and link it to a project and milestone.

The service fetches that page from Notion and parses it into a unified task model. At that point, it is no longer working with raw Notion properties. It is working with an internal task record that has fields like title, status, priority, relation IDs, and last modified time.

From there, the mapper translates platform-specific meaning. A Notion priority like **High** becomes the Linear priority value the target API expects. Status fields are interpreted into a common representation rather than passed through blindly.

The reconciler then compares that unified task against the matching Linear issue, if one already exists, plus any sync state that was saved from earlier runs. If no matching Linear issue exists, the result is a create operation targeting Linear. If the issue already exists but differs, it becomes an update. If both sides changed in incompatible ways, it becomes a conflict to resolve according to the configured strategy.

Once the decision is made, the task is serialized into Linear’s expected input shape and sent through the client. When Linear returns the new issue ID, the service stores that linkage locally so future runs know that the Notion page and Linear issue refer to the same task.

If the project or milestone relationship could not be fully applied in that first write, the relation resolver comes through later and reconnects it once the necessary IDs exist on both sides.

That is the whole system in miniature: normalize, compare, decide, write, reconnect, remember.

## **The Two Things That Made It Reliable**

Two parts of the system ended up mattering more than almost anything else: relationship handling and persistent sync state.

The relationship problem is easy to underestimate. A task can belong to a milestone. A milestone can belong to a project. A task can also have a parent task. If you try to sync every record independently in one pass, many of those references fail simply because the destination record does not exist yet.

The solution here was a two-pass strategy.

In the first pass, the service creates or updates base records without assuming every relationship can already be resolved. In the second pass, once cross-system IDs are known, it reconnects project, milestone, task, and subtask relationships using those mappings.

The state problem is just as important. Without local state, the engine has no durable memory. It can fetch data and compare timestamps, but it cannot really know what it created before, what changed semantically, or whether a record is genuinely new.

So the service keeps a local SQLite store with linked IDs, timestamps, content hashes, and last sync metadata. That gives the system continuity across runs. It can avoid duplicates, detect real changes more accurately, and treat sync as an ongoing process instead of starting from zero every time.

Those two pieces, relation resolution and state tracking, are what made the service feel stable rather than merely functional.

## **Making It Safe to Run**

Once the happy path worked, the next question was whether the system would behave well under normal failure conditions.

That meant building in retry logic with exponential backoff, handling rate limits explicitly for both APIs, supporting dry runs through the CLI, and keeping enough structured logging around each sync action to understand what happened later.

Conflict handling also had to be configurable. In a bidirectional sync, there is no universal answer to which side should win when both have changed. Depending on the workflow, the right answer might be last-write-wins, Notion-primary, or Linear-primary.

Those features are not as visible as the core data flow, but they are what make the tool usable in real workflows instead of only in controlled demos.

## **What I Learned Building It**

The main thing I took away from this project is that synchronization problems stop being API problems almost immediately.

At first, I thought most of the work would be in authentication, field mapping, and request logic. Those parts mattered, but they were not really the center of the challenge. The hard part was defining a stable internal model, preserving relationships across systems, deciding what changed in a way that held up over time, and keeping enough memory of earlier runs to avoid guessing.

In other words, the problem was less about moving data and more about establishing internal truth.

That shifted how I thought about the project. The APIs became edges. The architecture in the middle became the real product.

## **Learn More**

What started as a Notion–Linear integration turned into a much more interesting systems problem.

The service works because it does not try to force one tool to behave like the other. It gives both systems a shared internal language, uses that language to make sync decisions, and then translates those decisions back out carefully enough to preserve structure over time.

That ended up being the difference between a script that moves records and a system that can actually be trusted.

I write more about systems, product thinking, and technical design here: https://zachary-sturman.com
