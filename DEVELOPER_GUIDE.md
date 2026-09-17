# FileCortex Developer Guide

> Version: 7.0.0 | Updated: 2026-09-17 | Verification baseline: 882 passed, Ruff 0 errors

## Project Model

FileCortex is a local-first workspace context compiler. It exposes the same core behavior through four entry points:

```text
file_search.py       Tkinter desktop application
web_app.py           FastAPI application and WebSocket server
fctx.py              CLI
mcp_server.py        MCP tools
```

All entry points should delegate to `file_cortex_core/`; do not create a second implementation of file traversal, sandboxing, context formatting, or persistent configuration.

## Core Modules

| Module | Responsibility |
|---|---|
| `config.py` | Pydantic configuration, owner-aware inter-process lock, three-way merge, atomic persistence |
| `security.py` | project registration and real-path containment |
| `file_io.py` | traversal, gitignore, encoding detection, text/binary reads |
| `search.py` | Smart/exact/regex/content matching and bounded content-search execution |
| `context.py` | Markdown/XML context and truncation reporting |
| `actions.py` | file operations, ZIP extraction, progress, and external tools |
| `process_utils.py` | cross-platform process-tree termination |
| `duplicate.py` | hash-based duplicate detection |

`routers/` is an adapter layer, not a replacement business layer. Keep HTTP status mapping, request validation, and authentication there; move reusable workflows into the core or a future application-service layer.

## Non-Negotiable Invariants

1. Register roots only with `PathValidator.validate_project()`.
2. Resolve every user-controlled path against the registered root with `PathValidator.is_safe()` before reading, writing, executing, or returning it.
3. Revalidate generated destinations, not only request inputs. Regex replacement, archive output, extracted member, category destination, and symlink targets are all destinations.
4. A batch must either compensate on failure or return structured per-item failures. Never silently clear failed staging entries.
5. Any new persistent setting must be Pydantic-validated before save.
6. WebSocket producers must use bounded queues and stop/terminate handles.
7. Never rely on a source-tree resource being present in a wheel; declare every runtime asset in packaging metadata.
8. **Containment is not registration.** A path being *inside* `project_path` proves nothing until `project_path` itself resolves to a registered root (`get_valid_project_root`). Any endpoint that mutates project metadata (notes, tags, sessions, staging, settings) must run the registration gate first, otherwise `get_project_data_obj` silently auto-registers arbitrary directories — including system directories — and every other endpoint starts trusting them (v6.6.0 fix).
9. Reject UNC in both spellings: `\\server\share` **and** the long-prefix form `\\?\UNC\server\share`, and do it *before* any `resolve()`/`exists()` call — those calls themselves trigger SMB authentication (v6.6.0 fix).
10. `CancelledError` derives from `BaseException` on Python 3.8+. Any `except Exception` around `future.result()` is a latent crash; also note `as_completed()`/`wait()` never report futures already in the `CANCELLED` state — harvest `f.done()` explicitly before waiting (v6.6.0 fix).
11. Never derive security decisions from the client-controlled `Host` header (`request.base_url`). Compare origins against loopback hosts or an explicit allowlist (v6.6.0 fix).
12. WebSocket custom close codes require `accept()` first: closing before the handshake is answered with a bare HTTP 403 and the code never reaches the client (v6.6.0 fix).
13. Enum-ish request fields get `Literal` types and numeric fields get `ge/le` bounds in `routers/schemas.py` — free strings and unbounded ints silently corrupt behavior downstream (v6.6.0 fix).
14. Frontend: flush debounced persistence (`syncStagingToBackend.flushNow()`) *before* re-reading project state from the server, or the reload races the write and resurrects stale data (v6.6.0 fix).
15. WebSocket handshakes must run the origin gate (`_ws_handshake_allowed`), not only the token check — the HTTP middleware never executes for WS scopes, and browsers exempt WS from the same-origin policy (v6.6.1 fix).
16. Query project configuration with the **resolved** registered root, never the raw client path: `get_project_data()` auto-registers unknown keys, so a subdirectory input would create a phantom entry and resolve tools against defaults (v6.6.1 fix).
17. Delegated `click` handlers must not re-enter for checkboxes or SELECTs — those are `change`-driven; the click phase runs before state settles and with no arguments (v6.6.1 fix). Tk's `bind()` **replaces** a previous handler on the same widget/event: partition widgets or chain with `add="+"` consciously (v6.6.1 fix).
18. CLI path arguments are project-relative by contract: anchor relative paths to the resolved project root before `norm_path()` (which anchors to the CWD), and reflect execution failures in the process exit code (v6.6.1 fix).
19. Nested `.gitignore` files participate with git's last-match-wins precedence: evaluate each chain entry in order and let a child `!pattern` override a parent match. Never flatten multiple specs with a single `PathSpec.match_file()` call — it cannot express cross-file negation (v7.0 fix).
20. Windows shell quoting: `%%` collapsing only happens inside `.bat`/`.cmd` batch files; under `subprocess shell=True` (`cmd /c` command-line context) `%%` stays literal and corrupts paths containing `%`. Quote, but do not double percent signs (v7.0 fix).
21. Long synchronous I/O belongs off the serving thread: Web endpoints use `asyncio.to_thread` for exports/stats, and desktop callbacks use a worker thread + `root.after` — the Tk main thread must never read files, run exports, or rebuild filtered trees synchronously (v7.0 fix).
22. Queue-sentinel parity: every worker exit path (success, error, cancellation) leaves both an `("ERROR", msg)` where applicable **and** a terminal `("DONE", ...)`; consumers must be able to drain until DONE regardless of the outcome (v7.0 fix).
23. Deployment is single-process by contract: `ProgressTracker` is in-process state, so uvicorn must run with `--workers 1` (container CMD, systemd unit, and NSSM script all encode this). Relocate config/logs with `FCTX_CONFIG_DIR` instead of sharing `~/.filecortex`; expose `/healthz` (unauthenticated) for orchestrator probes (v7.0).

## Configuration and Persistence

`DataManager` supports a singleton for normal runtime and independent instances for tests:

```python
dm = DataManager()
isolated = DataManager.create()
with DataManager.activate(isolated):
    use_case(DataManager())
```

`get_project_data()` returns a snapshot dictionary. Use `get_project_data_obj()` only when a caller needs the live Pydantic object. Prefer a dedicated `update_*` method for mutations.

Saving uses this sequence:

```text
acquire owner-aware lock
  -> read latest disk config
  -> three-way merge (base / local / disk)
  -> Pydantic validate
  -> write temporary JSON
  -> os.replace
release only the lock owned by this process
```

The merge preserves independent edits. Concurrent edits to the same scalar key are local-wins by design. Do not treat JSON persistence as a multi-user database; add a real storage abstraction before supporting remote shared writes.

## Security and Web Deployment

By default the Web server binds to `127.0.0.1`. Local origins for the default port are allowlisted. Same-origin is decided by the Origin *host*: loopback hosts (`127.0.0.1`, `localhost`, `::1`) with any port, or an explicit `FCTX_ALLOWED_ORIGINS` entry — never by comparing against the request's `Host`-derived base URL. WebSocket handshakes apply the same policy via `_ws_handshake_allowed()` in `routers/ws_routes.py` (v6.6.1).

- If `FCTX_API_TOKEN` is configured, HTTP `/api/` requests require `X-API-Token`; WebSockets require `token` in the query string. Both comparisons encode to bytes before `hmac.compare_digest` (non-ASCII header values would raise `TypeError` on the raw-string variant).
- WebSocket auth failures `accept()` the handshake first and then `close(4001)`, so the custom code actually reaches browser clients.
- Binding a non-loopback host requires `FCTX_API_TOKEN`.
- `FCTX_PROD=1` hides exception details; it does not enable authentication.
- `FCTX_ALLOWED_ORIGINS` is a comma-separated explicit CORS override. Avoid `*` outside controlled local development.
- On shutdown the app lifespan terminates any tool subprocesses still tracked by `ProcessManager`; do not spawn long-lived children outside the registry.

When adding a route, apply the registered-root check **and** per-path containment before invoking core I/O — a single `verify_registered_path()` dependency is the planned convergence point (see docs/IMPLEMENTATION_PLAN_V660.md batch 2.1). When adding a new entry point, use the same registration and containment rules rather than duplicating string-prefix checks.

## Parameter Alignment

The detailed source-of-truth table is in [TECHNICAL_GUIDE.md](TECHNICAL_GUIDE.md). For each new parameter, update in this order:

1. Pydantic model in `file_cortex_core/config.py` if persistent.
2. Request schema in `routers/schemas.py` if exposed over Web.
3. API handler and core use case.
4. Frontend `state.js`, API wrapper, and form only when the Web UI owns it.
5. Tests covering model validation, route payload, and UI contract.
6. User/developer documentation.

Do not use JavaScript falsy fallback for valid numeric zero values. Validate numeric ranges in Pydantic and in the HTML form where possible.

## Testing and Quality Gates

```powershell
$env:TEMP = "E:\VScode\file_search\.pytest_tmp"
$env:TMP = $env:TEMP
pytest -q
ruff check .
python -m build --no-isolation
git diff --check
```

The temporary-directory override is useful on Windows hosts where the system drive lacks free space. Do not commit `.pytest_tmp`, `build/`, `dist/`, caches, or generated egg metadata.

Tests are layered by core behavior, API contracts, security, CLI persistence, MCP, file operations, and frontend source contracts. Add a behavior test near the responsible layer. Source-string frontend tests are useful regression guards but do not replace browser E2E tests for races and focus behavior.

Review reports for the v6.6.0 hardening round (architecture, positioning, full bug list, and the batched forward plan with per-fix test mapping) live in [`docs/`](docs/): `ARCHITECTURE_REVIEW.md`, `POSITIONING_ANALYSIS.md`, `CODE_REVIEW_V660.md`, and `IMPLEMENTATION_PLAN_V660.md`. The v6.6.1 bugfix round's ledger is `docs/CODE_REVIEW_V661.md`. The v7.0.0 master review, 41-item finding ledger, and release-engineering plan (with the implementation delivery record) is `docs/MASTER_REVIEW_AND_LANDING_PLAN.md`.

## Style and Review Rules

- `ruff check .` is the current mandatory lint gate.
- Use Google-style docstrings and type annotations for public Python interfaces. Annotation coverage is a review expectation; it is not yet a separate static-type CI gate.
- Use `logger.exception()` inside exception handlers when stack traces are needed.
- Escape dynamic HTML; Markdown must go through DOMPurify.
- Keep external command execution list-based and terminate child processes on disconnect/cancellation.
- Inspect the built wheel whenever packaging paths or static resources change.

## Release Checklist

- [ ] Full test suite passes.
- [ ] Ruff passes.
- [ ] Wheel and sdist build successfully.
- [ ] Wheel contains templates, static assets, and GUI modules.
- [ ] Version matches `pyproject.toml` and `file_cortex_core.__version__`.
- [ ] User docs, technical guide, roadmap, and test count agree.
- [ ] `git diff --check` is clean.
- [ ] Review staged diff and `git status` before commit/push.
