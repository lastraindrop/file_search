# FileCortex Current Engineering Plan

> Date: 2026-06-30  
> Scope: final repository state after File System Completion Tranches 1 & 2, frontend stabilization, and real progress wiring.  
> Goal: make FileCortex a lightweight, complete, locally usable file/workspace context system before expanding into heavier semantic-search/RAG features.  
> Status: ✅ Current Stabilization Tranche — COMPLETE. 768 tests passing, all gates green.

## 1. Executive Summary

FileCortex is already beyond a prototype. It has a microkernel core, four entry points, a FastAPI web UI, a Tkinter desktop UI, a CLI, an MCP server, and a substantial test suite. The main engineering risk is no longer absence of features; it is preserving reliability while the project grows.

The correct near-term direction is therefore **stabilization before expansion**:

1. Fix P0/P1 correctness, data-loss, and filesystem-safety defects.
2. Keep the current app lightweight: local-first JSON configuration, no mandatory database, no mandatory vector store, no cloud dependency.
3. Improve test coverage around the user-visible seams: CLI persistence, archive path safety, WebSocket tool execution, and shared search executor recovery.
4. Defer broad rewrites such as semantic search, RAG chat, UI framework replacement, plugin systems, and database migration until the existing system is proven dependable.

This document intentionally does **not** recreate the deleted historical review files. It is a current-stage plan and acceptance checklist for the repository as it stands now.

## 2. Product Direction and Positioning

### 2.1 What FileCortex Is

FileCortex is best positioned as a **local-first AI-era workspace/file context orchestrator**:

- It searches and stages project files.
- It exports selected files as AI-friendly Markdown/XML context.
- It performs safe file operations such as rename, move, archive, and categorize.
- It exposes the same workspace through desktop, web, CLI, and MCP interfaces.
- It is especially useful for developers and researchers preparing structured context for AI tools.

The strongest niche is not generic document chat. The strongest niche is:

> “Understand my local workspace, collect the right files safely, and produce reliable context for humans and AI agents.”

### 2.2 Comparable Tools and Lessons

| Tool / Category | Overlap | Lesson for FileCortex |
|---|---|---|
| FileSeek | Local AI-powered file archive/search | Lightweight local file tooling is viable, but CLI-only tools lack review/organization UX. |
| AiFileManager | AI classification, tagging, semantic search, RAG | Provider pluggability and local models matter; avoid making cloud AI mandatory. |
| TagSpaces | Offline tagging/file organization | Portable metadata is valuable; avoid locking core state into opaque formats too early. |
| Paperless-ngx | Mature document ingestion/classification | Inbox/review workflows are crucial for trust in automated classification. |
| Screenpipe | Local context capture | Event/pipeline architecture is powerful, but uncontrolled context capture can become heavy and privacy-sensitive. |
| Obsidian AI plugins | Markdown knowledge base + AI context | Markdown and plain files remain the best interoperability layer. |
| sqlite-memory | Hybrid semantic + FTS memory | If semantic search is added, hybrid vector + FTS is preferable to pure vector search. |
| Repomix | Repo-to-LLM context packing | FileCortex should win on interactive staging, safety, and multi-interface orchestration. |
| Aider / Continue / Cursor context tools | Developer AI context | FileCortex should complement IDE agents by being a local workspace context/control plane. |

### 2.3 Positioning Boundary

Do **not** try to compete first as “another RAG app.” The market is crowded. FileCortex should first be a dependable **context preparation and file orchestration layer**. Semantic search, embeddings, and chat are later enhancements, not the base identity.

## 3. Current Architecture Assessment

### 3.1 Runtime Shape

```text
User / Agent
  ├─ Tkinter desktop: file_search.py
  ├─ FastAPI web: web_app.py + routers/* + static/js/*
  ├─ CLI: fctx.py
  └─ MCP: mcp_server.py
        ↓
file_cortex_core/
  ├─ config.py        DataManager + Pydantic config models
  ├─ security.py      PathValidator sandbox
  ├─ file_io.py       filesystem walking, reading, encoding, gitignore
  ├─ search.py        smart/exact/regex/content search
  ├─ context.py       Markdown/XML AI context export
  ├─ actions.py       FileOps + ActionBridge subprocess execution
  ├─ duplicate.py     duplicate detection
  └─ format_utils.py  formatting helpers
```

### 3.2 Strengths

- **Microkernel core**: most behavior is centralized in `file_cortex_core/` and reused by entry points.
- **Local-first design**: no mandatory cloud dependency or external database.
- **Safety primitives exist**: `PathValidator`, route-level safety checks, and OOM/export limits provide a strong base.
- **Multiple integration surfaces**: web, desktop, CLI, and MCP give the tool practical reach.
- **Existing test culture**: the repository already has broad regression coverage and domain-specific test files.

### 3.3 Weaknesses

- **DataManager responsibility creep**: configuration persistence and project business operations are in one object.
- **Frontend and desktop monoliths**: `static/js/main.js` and `file_search.py` are large and harder to test in isolation.
- **Single JSON persistence ceiling**: sufficient for lightweight local use, but not ideal for multi-process or multi-user workflows.
- **Duplicated safety checks**: several routes perform similar project-root/path validation manually.
- **Mixed historical tests**: version-named test files preserve regressions but make ownership harder to understand.

These are important but not all urgent. The current tranche should fix correctness/security defects first, then schedule architectural cleanup.

## 4. Current Stabilization Tranche

### 4.1 Implemented / In Progress in This Tranche

| Area | Files | Purpose | Acceptance |
|---|---|---|---|
| CLI persistence and legacy fallback | `fctx.py`, `tests/test_cli_persistence_v10.py` | Ensure `fctx stage` and `fctx categorize` mutate the live `ProjectConfig`, not a `model_dump()` snapshot; ensure `fctx run` handles missing `custom_tools`. | ✅ Stage persists; categorize clears staging; both survive DataManager reload; legacy configs return a clean not-found message. |
| Archive output safety | `routers/fs_routes.py`, `tests/test_web_api.py` | Reject archive output traversal/separators and revalidate the final output path inside project root. | ✅ Malicious names rejected; safe names accepted inside root. |
| WebSocket tool fallback | `routers/ws_routes.py`, `tests/test_web_api.py` | Avoid `KeyError` when legacy/malformed project config lacks `custom_tools`. | ✅ Clean "Tool template not found" error over WebSocket. |
| Search executor robustness | `file_cortex_core/search.py`, `tests/test_search_engine.py`, `tests/test_coverage_fill.py` | Remove private `ThreadPoolExecutor._shutdown` dependency and recover from a shut-down pool via public `RuntimeError` behavior. | ✅ Content search survives a shut-down shared pool; no global dead executor leaks across tests. |
| **File System Completion Tranche 1** | `file_cortex_core/actions.py`, `routers/schemas.py`, `routers/fs_routes.py`, `fctx.py`, `static/js/*`, `templates/index.html`, `tests/*` | Safe copy/extract operations with no-overwrite, zip-slip protection, and security boundary enforcement. Batch copy support. | ✅ 764→768 tests. copy_item, extract_archive, batch API, copy/extract CLI, bulk Web UI. |
| **File System Completion Tranche 2** | Same files + `tests/test_web_api.py`, `tests/test_frontend_contract.py` | Transactional archive extraction (staging → atomic rename), ProgressTracker thread-safe registry, `/api/fs/progress` polling endpoints, real backend→frontend progress wiring. | ✅ 3-pass transactional extract, ProgressTracker class, progress API, frontend polling. |
| **Frontend Stabilization** | `static/js/main.js`, `static/js/api.js`, `static/js/state.js`, `templates/index.html`, `tests/test_frontend_contract.py` | Fix `indexOf` progress bug, `N selected` wording, double-submit guard, non-ZIP affordance, `bulkActions` d-flex regression; wire real `_pollProgress`; 4 new contract tests. | ✅ All FE-1 bugs fixed; FE-2 real progress wired end-to-end; visual QA confirmed. |

### 4.2 Explicit Non-Goals for This Tranche

- No semantic search/vector database implementation.
- No RAG/chat feature.
- No Electron/Tauri or frontend framework migration.
- No database migration from JSON to SQLite.
- No broad `DataManager` service extraction.
- No rewrite of Tkinter desktop UI.
- No plugin system or cloud sync.

## 5. Detailed Test Plan

### 5.1 Targeted Regression Tests

| Test target | Command | Expected result |
|---|---|---|
| CLI persistence | `python -m pytest tests/test_cli_persistence_v10.py -v` | All tests pass; stage/categorize persistence locked. |
| Archive API | `python -m pytest tests/test_web_api.py -k "archive" -v` | Malicious archive names rejected; safe names accepted. |
| WebSocket fallback | `python -m pytest tests/test_web_api.py -k "websocket or missing_custom_tools" -v` | Search WS still works; action WS handles missing `custom_tools`. |
| Search executor | `python -m pytest tests/test_search_engine.py tests/test_coverage_fill.py::TestSearchPoolShutdown -v` | Shared pool recovery tests pass. |

### 5.2 Broader Compatibility Tests

| Layer | Command | Purpose |
|---|---|---|
| Web/security | `python -m pytest tests/test_web_api.py tests/test_security_fixes_v650.py tests/test_security_resilience.py tests/test_security_v9.py -v` | Confirm API and security regressions remain green. |
| CLI/DataManager | `python -m pytest tests/test_cli_persistence_v10.py tests/test_comprehensive_v63.py tests/test_bugfix_v632.py tests/test_v8_comprehensive.py tests/test_dm_config.py -v` | Confirm CLI changes do not break existing config/CLI behavior. |
| Full suite | `python -m pytest` | Final release gate. |
| Lint | `python -m ruff check .` | Maintain Ruff 0 errors target. |

### 5.3 Manual Smoke Tests

1. `python fctx.py open .`
2. `python fctx.py stage . <known-file>`
3. `python fctx.py export . --format markdown --output context.md`
4. `python web_app.py` and open `http://127.0.0.1:8000`
5. Open a workspace, search for a file, stage it, archive a selection with a safe basename.
6. Try archive names like `../evil.zip` and `..\evil.zip`; verify rejection.

## 6. Architecture Roadmap

### Phase 0 — Current Stabilization ✅ COMPLETE

- ✅ Finish P0/P1 bug fixes listed above.
- ✅ File System Completion Tranche 1: safe copy/extract with no-overwrite, zip-slip, batch copy.
- ✅ File System Completion Tranche 2: transactional extract, ProgressTracker, progress API, frontend progress wiring.
- ✅ Frontend stabilization: FE-1 UX fixes, FE-2 real progress polling, visual QA.
- ✅ Run targeted tests, full tests (768 passed), and lint (ruff 0 errors, JS clean).
- ✅ Update this plan with actual verification evidence.

### Phase 1 — UX Enhancement & Hardening (Next)

- Add recent destination directories (localStorage) for copy/move/extract modals.
- Context-sensitive right-click menu (hide Extract ZIP for non-zips, show relevant actions by type).
- Operation result summaries (copied N items, failed M items with reasons).
- Pre-fill default destinations (current file parent, project root, remembered last destination).
- Keyboard shortcuts for bulk select-all (Ctrl+A in tree) and bulk stage.
- Lightweight operation history in localStorage.
- i18n preparation: extract hardcoded UI strings into a `strings` object.

### Phase 2 — Power Features (Later)

- Multi-archive processing with real per-file progress via `ProgressTracker`.
- File operation undo log (last-N operations with revert capability).
- Search result bulk actions (stage/copy from search overlay).
- Configurable destination presets (named save-locations).
- Web UI accessibility improvements (aria-labels, keyboard tree navigation, focus-visible styles).

### Phase 1 — Maintainability Cleanup

- Extract `DataManager` business operations into small service objects while keeping config persistence stable.
- Centralize route safety validation through dependencies/helpers to reduce repeated checks.
- Split `static/js/main.js` into feature modules: search, staging, file CRUD, context export, settings.
- Split desktop UI logic out of the largest `file_search.py` flows where tests can cover behavior.

### Phase 2 — Lightweight Usability Completion

- Improve first-run experience and workspace onboarding.
- Make CLI commands fully documented and regression-tested.
- Add a concise “daily workflow” guide: open → search → stage → export → categorize/archive.
- Ensure Windows/macOS/Linux behavior is covered by CI or documented limitations.

### Phase 3 — Optional AI Enhancements

Only after the stabilization and maintainability phases:

- Add hybrid search: full-text/FTS plus embeddings, not pure vector search.
- Support local-first model providers such as Ollama before cloud defaults.
- Add reviewable AI classification suggestions rather than irreversible automatic moves.
- Expose stable MCP tools for search, staging, export, and project metadata.

## 7. Risk Register

| Risk | Impact | Mitigation |
|---|---|---|
| Silent config data loss | User actions appear successful but do not persist | Use live `ProjectConfig` for mutating CLI paths; regression tests. |
| Filesystem traversal | Archive/file operations escape workspace | Reject separators/traversal and revalidate resolved target paths. |
| Legacy config crashes | Older configs miss keys expected by newer routes | Defensive `.get(..., default)` at route boundaries. |
| Shared executor shutdown | Content search fails due private executor state assumptions | Treat `RuntimeError` from `submit` as public signal and recover. |
| Over-expansion | Project becomes heavy before core is dependable | Keep semantic/RAG/database/UI rewrites out of the stabilization tranche. |

## 8. Completion Criteria

This tranche is complete when:

- All changed files have clean diagnostics.
- Targeted regression suites pass.
- Full `python -m pytest` passes, or any failures are clearly identified as pre-existing/unrelated.
- `python -m ruff check .` passes, or any failures are clearly identified as pre-existing/unrelated.
- The user-facing summary identifies files changed, tests run, and remaining roadmap items.
