---
title: Consolidating an Offline-First Episodic Memory System
action required: 🟠 Export
post on: Jul 21
write by: Apr 20
status: ready to publish
draft finalized?: Yes
exported?: No
pushed to articles repo?: No
scheduled: No
posted: No
projects: "Episodic Memory Agent (https://www.notion.so/Episodic-Memory-Agent-306aec944d3c800597abd4572f1ab679?pvs=21)"
one liner: This project is becoming a single offline-first episodic memory system that brings runtime, artifacts, and inspection into one coherent architecture, with location playing a central role in how memory is formed and understood.
tags: [Dashboard, Episodic Memory, Monty, Synthetic Memory, Thousand Brains Projects]
summary: This piece traces the consolidation of several related experiments into one canonical episodic memory project, built around a single Python package, a shared artifact contract, and a dashboard and notebook workflow that inspect the same persisted runs. It argues that memory systems become more useful when they are transparent, offline-first, and structured around evidence, decision traces, and revisitable artifacts rather than hidden runtime state. Running through all of it is a broader research view, that location and whereabouts are not secondary details, but central signals in how a system interprets scenes, updates memory, and reasons about revisitation.
series: Engineering AI for Recognition and Memory
platform: [DEV, Hashnode, Hashnoon, Medium]
cover_image: images/hero.png
Last edited time: "April 11, 2026 5:21 PM"
dash for layout: -
updatedAt: 2026-04-11
---

There is a point in some projects where separate experiments stop feeling separate, and start revealing themselves as parts of the same system.

That is where this project is now.

What began as several lines of work around episodic memory, working memory, panorama-based location identification, observability, notebooks, and dashboard inspection is starting to converge into one canonical project: a single offline-first episodic memory system with one runtime, one artifact contract, and one coherent way to inspect what happened.

This is not a finished system. It is still very much a work in progress, and that is part of why I wanted to write this now.

I wanted to document not only what the project currently is, but also how I am thinking about it, what I decided to merge, what I chose to defer, what seems most important right now, and why I keep coming back to the idea that location and whereabouts are central to building useful memory systems.

![High level arch.png](images/High_level_arch.png)

## The Current Shape of the Project

The project is now converging around one canonical Python package, `episodic_memory`, and one canonical web app in `dashboard/`.

At a practical level, that means I am no longer treating the root package, the working-memory subsystem, and the legacy episodic-memory-agent as separate active products. Instead, I am absorbing the useful parts into one architecture.

- one canonical Python package at `src/episodic_memory/`

- one canonical Next.js dashboard in `dashboard/`

- one notebook workspace in `notebooks/`

- archived legacy systems in `archive/`

The important change is not really the directory layout. It is the conceptual shift. I want one project with one truth surface, rather than several parallel implementations carrying overlapping ideas.

The merged project is offline-first and organized around a single run artifact bundle. That bundle is what the notebooks read, what the inspector API serves, and what the dashboard renders. In other words, analysis and UI are peers over the same persisted data, rather than two disconnected interpretations of runtime state.

That feels like the right foundation.

![repo structure.png](images/repo_structure.png)

## What the System Does Right Now

At the moment, the canonical runtime supports two active modes end to end:

- **stub mode**, for deterministic scenario execution

- **panorama mode**, for image or video exploration tied to location identification

Every run produces one canonical bundle containing files such as:

- `manifest.json`

- `summary.json`

- `memories.json`

- `graph.json`

- `events.jsonl`

- `memory_decisions.jsonl`

- `steps/step_XXXX.snapshot.json`

That bundle is the contract.

This matters a lot to me because one of the recurring problems in experimental cognitive systems is that the runtime may be doing interesting things, but the inspection surface is brittle, partial, or too tightly coupled to internals. I want the opposite. I want runs to be inspectable after the fact, replayable in a meaningful way, and transparent enough that I can understand not just what the system concluded, but why.

So this project is as much about memory transparency as it is about memory itself.

Each canonical step snapshot records things like:

- location hypotheses

- match evaluation

- evidence bundle

- memory delta

- graph state

- candidate ideas

- writeback candidates

- write decisions

- node lifecycle changes

- debug records

That means the project is not just building memory. It is building an inspectable trace of memory formation, and also of memory refusal.

That distinction matters.

## Why I Merged Everything Into One Canonical Project

One of the biggest decisions I made was to stop preserving the old boundaries as if they were permanent.

At one point, I had:

- root cognition, working-memory, and transparency work

- a separate working-memory subsystem identity

- a legacy panorama and location-identification codebase

- separate inspection habits across notebooks and dashboard

That structure made sense while the ideas were still exploratory. Over time, though, it started creating the wrong incentives. There was too much translation, too many implied contracts, and too many places where one surface knew something another surface did not.

So the decision became straightforward:

**one active package, one active dashboard, one artifact model, one pipeline**

This is a clean break. It is not a compatibility-first architecture. It is a coherence-first architecture.

That also meant making a few related decisions:

- old public package names should not remain as long-term compatibility shims

- the working-memory subsystem should be absorbed, not preserved as a separate installable identity

- the legacy episodic-memory-agent should be archived once the useful ideas and import paths are absorbed

- Unity should remain part of the long-term plan, but not be required for the first merged version

That last decision matters more than it may seem.

A project like this can easily become a hostage to future ambition. I do not want Unity integration, embodied simulation, or future interaction loops to block progress on the core questions. So I am preserving the architectural slot for Unity, but explicitly deferring it in v1.

That keeps the current work honest: build the canonical memory runtime first, make it observable, make it testable, make it inspectable, then expand.

![software ingest.png](images/software_ingest.png)

## The Core Idea I Keep Returning To: Location Matters

A major influence on this project is the Thousand Brains Project and Monty. Their work is grounded in the idea that intelligence is sensorimotor, structured, and deeply tied to how repeated cortical units model the world. Monty is presented as an implementation of a thousand-brains system, with a strong connection to cortical columns as repeating computational units.

I think that framing is directionally right.

More specifically, I think their emphasis on cortical columns, sensorimotor learning, and structure over unstructured pattern matching points toward something important. Their work resonates with how I have been thinking about this space.

Where I keep focusing, though, is on location and whereabouts as an especially important part of the system.

Not necessarily as the first step in a strict sequence, and maybe not even as a separate step at all.

I think of it more as a concurrent process that develops alongside object recognition and pose estimation.

That is increasingly how I see it:

- object

- pose

- location

- relation

- revisitation

- memory update

These may not be serial modules so much as mutually constraining signals.

When a system is trying to determine what it is looking at, it is also learning where it is, what viewpoint it has, what changed since the last encounter, and whether the current scene matches a stable memory or represents something novel. In practice, location and object understanding seem tightly entangled.

That is one reason this project currently emphasizes panorama and location-memory behavior. The system scans, extracts features, builds embeddings, compares them to stored location memories, and then decides whether it is revisiting something known or encountering something new enough to justify a memory update.

That may sound narrower than “general intelligence,” but I do not think it is narrow in the wrong way. I think it is one of the most grounding places to start.

![1.png](images/1.png)

## The Way I Am Thinking About It So Far

One thing I have become more convinced of is that useful memory systems should not be treated as a black box sitting after perception.

Memory has to be part of the interpretation pipeline itself.

That has led me back to a few recurring principles.

### 1. One pipeline should handle multiple input modes

Stub scenarios and panorama exploration should not become separate worlds. They should normalize into the same observation and evidence model, then flow through one shared pipeline.

That shared pipeline should cover:

- perception or input normalization

- location matching

- working-memory update

- write-decision evaluation

- artifact emission

This makes the system easier to reason about, and it makes cross-mode comparison possible.

### 2. Memory should be inspectable, not merely stored

A saved memory without context is not enough.

- what candidates existed

- what evidence was considered

- what was skipped

- what was written

- how graph state changed

- what confidence or match structure led to the decision

So transparency is not a side feature here. It is part of the architecture.

### 3. Jupyter and the dashboard should inspect the same reality

I do not want notebooks to be the “real” place where understanding happens while the dashboard becomes a thinner or less truthful surface. I also do not want the opposite.

The notebooks and dashboard should be peers over one persisted artifact contract.

That is why the dashboard reads through a file-backed inspector API rather than importing arbitrary runtime state directly.

### 4. Legacy work should remain explorable without staying active

Some of the older work still matters, but that does not mean it should stay in the active install path forever.

Instead of preserving old systems as living parallel products, I want import paths that convert legacy runs into the canonical bundle format. That way old runs remain inspectable without forcing the project to carry multiple active architectures indefinitely.

### 5. Unity matters, but it is not the bottleneck right now

Embodiment matters. Simulation matters. Interaction matters.

But right now the bottleneck is not whether the system can run in Unity. The bottleneck is whether I have a canonical memory architecture that is inspectable and stable enough to justify a richer embodiment layer.

So Unity remains on the architectural horizon, but not in the critical path for this version.

## What Has Already Been Decided

A lot of the project is still fluid, but some decisions now feel firm enough to state clearly.

### The canonical public surface

The project’s public Python identity is `episodic_memory`, and the CLI is `episodic-memory`.

That may sound small, but naming matters. It signals where the center of gravity is now.

### The canonical layout

- `episodic_memory.inputs`

- `episodic_memory.pipeline`

- `episodic_memory.memory`

- `episodic_memory.artifacts`

- `episodic_memory.inspector`

- `episodic_memory.wm`

This is the architecture I want to build on top of, rather than around.

### The canonical execution model

The execution model is intentionally straightforward:

1. an input mode produces normalized observation data

2. the working-memory engine updates graph state and decision traces

3. the location-memory store maintains records, matches, and deltas

4. a canonical step snapshot is emitted

5. the artifact writer persists the run bundle

6. notebooks, the inspector API, and the dashboard inspect those files

That is the project in one sentence.

### The canonical notebooks

- pipeline workspace

- memory explorer

- run comparison and dashboard parity

These are not side utilities. They are part of the development surface of the system.

### The dashboard scope

The dashboard is read-only by design right now. It exists to inspect:

- run summaries

- timeline

- memories

- graph and topology

- evidence and matches

- save and skip decisions

This is an inspection system, not yet a control room.

## What Is Still Unresolved

Because this is still a work in progress, it helps to be explicit about what is not finished.

I am still working through questions such as:

- how rich the memory-detail rendering should become

- how best to compare bundles for regression analysis

- how much panorama-specific interpretability should be preserved directly in the dashboard

- how to calibrate match behavior across more varied scenes

- how much graph state is enough for transparency without overwhelming the inspection surface

- how Unity should eventually plug in without distorting the canonical artifact contract

There is also a deeper unresolved question underneath the implementation work:

**What should count as a memory unit in a system like this?**

Is it a location?

A revisitable scene?

A graph substructure?

An object-place relation?

A sensorimotor hypothesis that proved stable enough to retain?

I do not think I have a final answer yet. What I do know is that I want the system to preserve enough evidence and enough decision history that I can move toward that answer empirically, rather than only philosophically.

## Why This Is Offline-First

I keep returning to offline-first design because it imposes a discipline that research systems often avoid.

If the system has to produce a persisted run bundle that stands on its own, then:

- the contract has to be real

- the evidence has to be portable

- the inspector has to be decoupled

- the dashboard has to render from artifacts, not hidden runtime assumptions

- notebooks have to operate on the same saved outputs as everything else

In other words, offline-first architecture forces honesty.

That honesty is valuable for debugging, for comparison, for importing older runs, and eventually for any serious evaluation workflow.

## Where This Is Going Next

The longer-term direction is fairly clear, even if the exact path is still changing.

### Near term

The immediate goal is to stabilize the canonical stub and panorama modes, keep notebooks and dashboard aligned on the same artifact contract, and improve panorama matching calibration across more varied scenes.

That is the practical next step.

### Medium term

The next layer after that is richer memory-detail rendering, stronger bundle diff tooling, and better regression analysis across runs.

That is where the system becomes not just inspectable, but comparable.

### Longer term

Longer term, I want to reintroduce Unity through a canonical adapter slot while preserving the same bundle and inspector surfaces.

That matters because I do not want embodiment support to split the architecture back apart. If Unity returns, it should return as another producer of canonical runs, not as a competing universe.

Beyond the concrete roadmap is the broader research direction behind all of this.

I want to keep exploring whether episodic memory, location memory, working memory, and perceptual inference can be brought closer together in a system that feels more biologically grounded without becoming vague.

That is also why I keep returning to Thousand Brains and Monty. Their framing of intelligence as sensorimotor and structurally grounded continues to feel important to me, especially the emphasis on cortical columns and distributed modeling.

My own emphasis, at least in this phase, is that location and whereabouts should be treated as first-class signals in that story. Not as an afterthought, and not as metadata, but as part of how the system decides what it is encountering and whether that encounter should become memory.

![Runtime vs artifact.png](images/Runtime_vs_artifact.png)

## Why I Am Publishing This Before It Is Done

Because this project is not just a codebase. It is also an evolving theory of what matters in memory-centric AI systems.

Publishing while it is still unfinished does two useful things for me.

First, it forces me to state the architecture clearly enough that I can see whether it actually holds together.

Second, it preserves the reasoning behind the project while that reasoning is still active and changing.

Too many project writeups happen after the fact and make the final architecture look inevitable. That is almost never true. In this case, the actual story is messier, and I think more useful:

- multiple active threads of work

- a decision to unify them

- a belief that transparency matters

- a growing conviction that location is central

- a deliberate choice not to let future embodiment concerns block present architectural coherence

That is the real work in progress.

And that is the part I most want documented.

![Sketch ideas.png](images/Sketch_ideas.png)

## Closing

So this is where the project stands right now:

a single canonical episodic memory system, still under construction, organized around one package, one dashboard, one artifact contract, and one increasingly clear idea, that memory, location, evidence, and working state should belong to the same inspectable system.

I do not think this is the final form of the project.

But I do think it is the right consolidation.

And I think getting this part right, especially the handling of location, revisitation, evidence, and write decisions, will make everything that comes later more grounded.

That includes richer perception.

That includes object and pose integration.

That includes Unity.

And that includes any larger theory about how episodic systems should work.

For now, this is the work: make the memory system coherent, transparent, and real enough to inspect.

Everything else can build on that.

![publis api.png](images/publis_api.png)

## Explore the Repository

If you want to see the project itself, the repository is here:

**GitHub Repo:** [https://github.com/ZSturman/Episodic-Memory-Agent](https://github.com/ZSturman/Episodic-Memory-Agent)

The codebase reflects the same transition described in this post, from separate lines of work toward one more coherent episodic memory architecture. That context may make the repository easier to navigate, especially if you are interested in the runtime, artifact structure, or inspection surfaces.

If you want the earlier, narrower stepping stone into this same line of work, I wrote about that here: [https://zachary-sturman.com/articles/building-a-location-first-learning-agent-to-explore-context-memory-and-consciousness](https://zachary-sturman.com/articles/building-a-location-first-learning-agent-to-explore-context-memory-and-consciousness).

