# FileCortex Current Engineering Plan

> Version: 6.6.0 | Updated: 2026-09-06 | Verification baseline: 846 passed, Ruff 0 errors, wheel/sdist built

## Purpose

FileCortex is a local-first workspace context compiler and file-operation control plane. It helps users search a workspace, stage relevant files, export deterministic AI context, and perform reviewed file operations through desktop, Web, CLI, and MCP entry points.

The product is not a general cloud RAG chat application and should not become one by default. Original files remain the source of truth; the application stores only configuration and workspace metadata.

## Current State

The P0/P1/P2 remediation tranche is complete.

- P0: Web trust boundary, project containment, destructive file operations, preview safety, packaging resources, and staging data loss.
- P1: cross-process configuration merge, batch copy/extract recovery, ZIP resource limits, structured categorization failures, and bounded WebSocket transport.
- P2: XML validity, context truncation visibility, search backpressure and tag behavior, frontend request generations, progress polling, and UI consistency.

The v6.5.3 review-driven round is complete as well: Windows lock liveness probe, corrupt-config recovery, desktop preset Pydantic compatibility, case-only rename, case-faithful excludes, gitignore directory rules in the tree view, null-tolerant settings API, CLI exit codes, per-entry-point search-size alignment, WebSocket 3.10 backpressure compatibility, CORS preflight, and threaded desktop/MCP tool execution. See TECHNICAL_GUIDE §9.1 for the full fix archive.

The v6.6.0 full-architecture review round is complete: UNC long-prefix bypass (validate_project/is_safe), note/tag auto-registration sandbox escape, MCP transport wiring, POSIX process-group self-kill, corrupt-config backup-before-rewrite, search CancelledError/future-drain and backpressure cancellation, manual-exclude separator parity, metadata fallback contract, WS error/closing-code delivery, origin hardening against Host spoofing, extract UNC source blocking, lifespan process cleanup, and a batch of frontend/desktop race and UX fixes. Full findings and follow-ups live in `docs/` (ARCHITECTURE_REVIEW, POSITIONING_ANALYSIS, CODE_REVIEW_V660, IMPLEMENTATION_PLAN_V660). Baseline: 846 passed, Ruff 0 errors.

The next work is deliberate product improvement, not another broad stabilization rewrite.

## Architecture Snapshot

```text
Desktop Tkinter / Web FastAPI + ES modules / CLI / MCP
                         |
                    routers + services
                         |
 file_cortex_core: config, security, file_io, search, context, actions
                         |
             local files + ~/.filecortex/config.json
```

Cross-cutting invariants:

1. A project must be registered through `PathValidator.validate_project()`. Registration is the only path into `config.projects`; path containment never auto-registers (v6.6.0).
2. Any path used for a destructive or content-reading operation must pass `PathValidator.is_safe()` against its registered root. UNC paths are rejected in both spellings (`\\server\share` and `\\?\UNC\server\share`) before any filesystem call that could trigger SMB (v6.6.0).
3. User-visible mutations must either be atomic or report per-item outcomes and preserve failed staging entries.
4. Configuration writes use an inter-process lock, three-way merge, temporary file, and `os.replace()`.
5. The same behavior must be exposed consistently through Web, GUI, CLI, and MCP where applicable.

## Delivery Plan

> The concrete execution schedule — batches 2.0 (leftover P2s), 2.1 (structural refactor with behavior-preserving guard), 2.2 (release engineering), 3.x (context compiler), 4.x (optional local index) — with per-batch locations, changes, and acceptance tests lives in [docs/IMPLEMENTATION_PLAN_V660.md](docs/IMPLEMENTATION_PLAN_V660.md) §4. The strategic rationale behind these phases is in [docs/POSITIONING_ANALYSIS.md](docs/POSITIONING_ANALYSIS.md) §5.

### Phase 1: Usability and Accessibility

Goal: make existing safe functions easier to use without adding a new storage or AI platform.

- Recent destination directories and destination presets for copy/move/extract.
- Context-sensitive menu actions and clear per-item operation summaries.
- Keyboard navigation, ARIA tree/menu semantics, focus restoration, and visual focus states.
- First-run workspace onboarding and a concise daily workflow guide.
- Operation history with source, destination, time, outcome, and links to affected files.

Acceptance: no destructive operation has an ambiguous target; every batch result gives completed/skipped/failed counts and reasons.

### Phase 2: Maintainability and Release Engineering

Goal: reduce the cost and risk of future feature work.

- Extract application services from route handlers and `DataManager` while preserving public behavior.
- Split `static/js/main.js` by search, staging, preview/editor, file operations, and settings.
- Split the largest desktop-controller workflows into testable collaborators.
- Add Windows and macOS CI, real wheel-install smoke tests, and browser E2E coverage.
- Enable gradual static type checking for core and route modules.

Acceptance: all release artifacts are installed and smoke-tested in a clean environment; platform-sensitive behavior is exercised on Windows CI.

### Phase 3: Context Compiler Quality

Goal: improve AI context quality before adding a chat product.

- Stable JSON context manifest with path, hash, size, token count, truncation, and selection reason.
- Exact tokenizer support and hard token budgets.
- Tree-sitter symbol maps and `full` / `symbols` / `tree-only` / `exclude` detail levels.
- Git diff and change-aware ranking; dynamic repository map inspired by Aider.
- Secret scanning and export reports.

Acceptance: identical input/configuration produces a deterministic manifest; every exported file has a reason and truncation state.

### Phase 4: Optional Local Index and Reviewed Organization

Goal: support large mixed workspaces without unsafe automation.

- SQLite manifest plus FTS5 for incremental filename, content, and symbol search.
- Optional embeddings and reranking, never mandatory cloud infrastructure.
- PDF/DOCX/HTML parsing as optional capabilities; OCR remains optional.
- Rule-first and model-assisted categorization plans with dry-run, conflict preview, audit log, and undo.

Acceptance: model suggestions never move or delete files until a user approves a concrete plan.

## Explicit Non-Goals

- No mandatory cloud model, vector database, or account.
- No automatic destructive AI actions.
- No replacement for a user’s primary file manager, IDE, or RAG/chat platform.
- No database migration until JSON configuration limits are demonstrated by real usage.

## Release Gate

Before each release:

1. Run `pytest -q` with a writable temporary directory.
2. Run `ruff check .`.
3. Run `python -m build --no-isolation` and inspect the wheel for templates, static assets, and GUI modules.
4. Verify version, test-count, security-default, and parameter tables in documentation.
5. Review `git diff --check`, `git status`, and the complete staged diff before commit.
