# FileCortex Developer Guide

> Version: 6.5.3 | Updated: 2026-08-23 | Verification baseline: 800 passed, Ruff 0 errors

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

By default the Web server binds to `127.0.0.1`. Local origins for the default port are allowlisted. Same-origin requests work on any selected `--port`.

- If `FCTX_API_TOKEN` is configured, HTTP `/api/` requests require `X-API-Token`; WebSockets require `token` in the query string. Both comparisons use `hmac.compare_digest`.
- Binding a non-loopback host requires `FCTX_API_TOKEN`.
- `FCTX_PROD=1` hides exception details; it does not enable authentication.
- `FCTX_ALLOWED_ORIGINS` is a comma-separated explicit CORS override. Avoid `*` outside controlled local development.

When adding a route, apply the registered-root check before invoking core I/O. When adding a new entry point, use the same registration and containment rules rather than duplicating string-prefix checks.

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
