# FileCortex Technical Guide

> Version: 6.5.3 | Updated: 2026-08-23 | Verification baseline: 800 passed, Ruff 0 errors

## 1. What the System Does

FileCortex compiles a local workspace into reviewed, bounded AI context and provides safe file workflows around it. It does not call a hosted model itself. Its AI-facing outputs are Markdown/XML context, project blueprints, prompt templates, token estimates, and MCP tools.

```text
discover -> search -> stage -> inspect -> export context -> use with an AI tool
                              |
                       copy / archive / classify / run approved tool
```

The source filesystem remains authoritative. Configuration, staging, tags, notes, sessions, categories, and tool templates are stored in `~/.filecortex/config.json`.

## 2. Runtime Architecture

```text
Tkinter GUI     Web UI + REST/WS     CLI     MCP
       \             |                |       /
        \------------+----------------+------/
                     |
              file_cortex_core
 config | security | file_io | search | context | actions
                     |
         local workspace + config.json + child processes
```

### Entry Points

| Entry | Role |
|---|---|
| `file_search.py` | desktop user interface |
| `web_app.py` | FastAPI app, CSP, CORS, HTTP auth, templates/static assets |
| `fctx.py` | scriptable workspace operations |
| `mcp_server.py` | tools for external AI agents |

### Core Execution Paths

**Workspace open**

```text
input root -> validate_project -> add recent -> create ProjectConfig -> save
```

**Search**

```text
SearchQuery -> PathMatcher / ContentMatcher -> walk_filtered
  -> gitignore/manual excludes -> bounded content futures -> result metadata
```

**Context export**

```text
staged paths -> containment check -> flatten directories -> binary filter
  -> read bounded text -> optional NoiseReducer -> Markdown or XML -> token estimate
```

**File operation**

```text
request -> registered root -> real-path containment -> core FileOps
  -> progress/result -> UI/CLI/MCP response
```

## 3. Security Model

### 3.1 Workspace Containment

`PathValidator.validate_project()` rejects missing, file, system, sensitive, and Windows UNC roots. `PathValidator.is_safe(target, root)` resolves paths before containment comparison, so an in-project symlink cannot authorize its external target.

Every path is checked twice where it matters:

1. The adapter checks the request path against a registered project root.
2. Core operations validate generated or resolved targets such as rename results, archive output, category destinations, copy destinations, and ZIP members.

Never replace this with `startswith()`, normalized-string comparison, or a frontend-only check.

### 3.2 Web Trust Boundary

- The default listener is `127.0.0.1:8000`.
- Default CORS allows the standard loopback origins. Same-origin requests are permitted for a custom Web port.
- Binding outside loopback requires `FCTX_API_TOKEN`.
- When configured, HTTP uses `X-API-Token`; WebSocket uses the `token` query parameter; both use constant-time comparison.
- `FCTX_PROD=1` hides unexpected exception details only.

This is a local application security model, not a multi-user authorization system. A network deployment requires a token, explicit origins, TLS/reverse-proxy policy, and an operational threat-model review.

### 3.3 File and Archive Safety

- Single item names reject separators and `.`/`..`.
- Batch rename validates each regex-generated name and resolved destination.
- Archive output cannot overwrite an existing file or overlap its selected source.
- ZIP extraction rejects absolute, UNC, drive, and traversal names; duplicate or existing targets; excessive member count, member size, total uncompressed bytes, and compression ratio.
- Copy rolls back completed targets on a later failure. Extraction stages files and compensates committed files/directories on commit failure.

## 4. Configuration Consistency

`AppConfig`, `ProjectConfig`, and `GlobalSettings` are Pydantic models. Ranges are enforced for preview size, token budget, token ratio, and project search size.

### 4.1 Persistent Update Flow

```text
route/schema validation
  -> DataManager update method
  -> base/local/disk three-way merge under owner-aware lock
  -> AppConfig validation
  -> temporary JSON write
  -> os.replace
```

The merge preserves independent edits from GUI, Web, CLI, and MCP processes. For a conflicting scalar update, the local writer wins. Staging/recent/pinned lists are unioned. This is adequate for local cooperating processes, not for collaborative multi-host editing.

### 4.2 Snapshot Rule

`get_project_data()` returns a `model_dump()` snapshot. Mutating it does not persist. Use `get_project_data_obj()` only for a live model or, preferably, an explicit `update_*` operation followed by save.

## 5. Parameter Alignment

The model is the backend source of truth; frontend defaults are only initial display values. A parameter change is complete only after its model, schema, route, frontend, tests, and documentation agree.

| Parameter | Backend authority | Web path | Default / constraint |
|---|---|---|---|
| `token_threshold` | `GlobalSettings` | `/api/global/settings` | 128000, 1..10000000 |
| `token_ratio` | `GlobalSettings` | `/api/global/settings` | 4.0, >0..100 |
| `preview_limit_mb` | `GlobalSettings` | `/api/global/settings` | 1.0, >0..100 |
| `max_search_size_mb` | `ProjectConfig` | `/api/project/settings` and WS search | 10, 1..1024 |
| `enable_noise_reducer` | `GlobalSettings` | default for `/api/generate` | false |
| `apply_noise_reducer` | `GenerateRequest` | `/api/generate` | null means use global setting |
| `FCTX_API_TOKEN` | environment | HTTP header / WS query | unset only for loopback mode |
| `FCTX_ALLOWED_ORIGINS` | environment | CORS middleware | loopback origins by default |
| `__version__` | `file_cortex_core.__version__` | Jinja template | 6.5.3 |

### 5.1 Dynamic Default Alignment

Default values are a live contract, not copy-pasted constants:

- Persistent defaults are read from the Pydantic models (`GlobalSettings()`, `ProjectConfig()`) at runtime. Tests assert against model instances and `__version__`, never hard-coded numbers, so changing a default updates the contract instead of silently breaking or faking tests.
- `max_search_size_mb` is resolved per entry point from the project's registered configuration: `fctx.py`, `mcp_server.py`, and the WebSocket search all read `proj_data["max_search_size_mb"]` with a fallback equal to the `ProjectConfig` default (10, range 1..1024). The module-level `DEFAULT_MAX_SIZE_MB` (5) is only the unconfigured `SearchQuery` fallback. Changing the model default requires updating all three call-site fallbacks together — this was aligned in v6.5.3 after the CLI/MCP paths were found using the module default while the Web path used the project value.
- `__version__` is injected into the Web template and asserted by tests, so version bumps are verified rather than assumed.
- Frontend inputs display model defaults but the backend remains authoritative; numeric inputs use `parseInt(...) || <default>` which must never silently accept an out-of-range value such as `0`.

When changing any parameter, follow the checklist in §5 and add one regression test that reads the value from the backend model.

### 5.2 Case Sensitivity Semantics

Case handling follows the filesystem's native semantics per platform; there is no unconditional `lower()` normalization:

- Exclude patterns (`*.log`, `build/`) are case-sensitive on POSIX and case-insensitive on Windows, matching how `gitignore` behaves on each platform. The search query has an explicit `case_sensitive` flag that applies to query text matching.
- Rename operations compare existing targets with `os.path.normcase()`: a case-only rename (`a.txt` -> `A.txt`) is allowed on case-insensitive filesystems instead of being reported as a conflict.
- Path containment (`PathValidator.is_safe`) uses `os.path.normcase()` on Windows so `C:\Foo` and `c:\foo` compare equal.
- WebSocket search results are normalized with `PathValidator.norm_path()` before enqueue, so staging never receives duplicated variants of the same path.

The key validation chain is:

```text
form/state.js -> api.js -> routers/schemas.py -> route -> config/core -> tests
```

Avoid these historical failure modes:

- JavaScript `value || default` treating `0` as absent.
- Pydantic fields without range constraints.
- `setattr()` bypassing model validation.
- UI success messages after a backend whitelist silently drops fields.
- one UI save split into multiple independent persistence requests.
- Unconditional `lower()` on exclude patterns: breaks case-faithful paths on POSIX. Case semantics are platform-defined, see §5.2.
- Treating disk configuration as trustworthy: a corrupt or out-of-range `config.json` must be rejected and the file rewritten from in-memory state, otherwise every later save bricks permanently.
- Reporting a case-only rename (`a.txt` -> `A.txt`) as a conflict: compare candidate paths with `os.path.normcase()` first, see §5.2.
- CLI failure paths exiting with code 0: every `cmd_*` handler returns a boolean and `main()` calls `sys.exit(1)` on failure so scripts can detect errors programmatically.
- Assuming `TimeoutError` is unified across Python versions: 3.10's `concurrent.futures.TimeoutError` is a distinct type, catch both.
- Letting a UI value `NaN` reach the backend as a setting: the API treats `null` as "no change" and the frontend guards NaN before sending.

## 6. Search and Streaming

`PathMatcher` applies explicit positive/negative tags consistently in smart, exact, regex, and content flows. Smart mode derives path keywords from the query; other modes preserve their query semantics and apply only explicit tags.

Content search shares a thread pool but limits in-flight futures. Once the threshold is reached, the iterator waits for a completion before submitting another read. Cancellation avoids waiting for the remaining futures.

WebSocket search and tool execution use bounded async queues. Producer threads block while a slow client consumes data, instead of allocating an unbounded result list. Disconnect and error paths set stop signals and terminate registered tool processes. Backpressure waits catch both the builtin `TimeoutError` (3.11+) and `concurrent.futures.TimeoutError` (3.10), so the 3.10 support tier behaves identically.

## 7. Context Formats and Limits

Markdown uses a prompt prefix followed by fenced file blocks. XML is a valid single-root document:

```xml
<filecortex>
  <instruction><![CDATA[optional prompt]]></instruction>
  <blueprint><![CDATA[optional ASCII tree]]></blueprint>
  <context>
    <file path="relative/path.py" size="1.2KB"><![CDATA[source]]></file>
  </context>
</filecortex>
```

CDATA terminators are split safely; XML path attributes are escaped. File count is capped at 500, total content at 50 MiB, and each read is capped at 1 MiB or remaining export budget. Output includes file-level and export-level truncation indicators rather than silently claiming completeness.

Token estimates are heuristic, not model-tokenizer exact. Future context-compiler work should add model-specific tokenization and an export manifest.

## 8. UI State Rules

- Preview requests carry a generation id. A late response cannot overwrite a newer file selection.
- Large/binary previews are view-only; saving must use a full, verified read path in a future editor enhancement.
- Search WebSockets have a generation id; stale messages cannot alter a newer search result set.
- Staging is the data model; GUI filtering is only a view. Never write a filtered view back as the full staging list.
- Progress polling allows one in-flight request per task and checks task ownership before updating shared UI.

## 9. Testing Strategy

The suite has 800 tests across unit, integration, Web/API, CLI, MCP, security, packaging, file-operation, and frontend contract layers.

Important regression families:

| Area | Representative coverage |
|---|---|
| containment | external context paths, symlink paths, rename traversal, archive targets |
| persistence | snapshot isolation, independent instance merge, schema ranges |
| file operations | copy rollback, ZIP slip, ZIP resource limits, conflict behavior |
| context | CDATA, XML parsing, truncation, noise reducer |
| search | four modes, tags, cancellation, shared-pool recovery |
| frontend | preview/search race guards, staging sync, progress contract |
| packaging | entry modules, runtime assets, versions, docs test-count consistency |
| v6.5.3 fixes | Windows lock probe, preset Pydantic compat, corrupt-config recovery, case-only rename, null-setting tolerance, gitignore directory rules, case-faithful excludes, ZIP slash names, CLI exit codes, search-size alignment, WS 3.10 backpressure, threaded desktop tools |

### 9.1 v6.5.3 Fix Archive (process and results)

The v6.5.3 round started from a full-repo review that produced a numbered bug list (B1-B20) plus enhancement notes (A1-A7), then applied each fix with a dedicated regression test in `tests/test_bugfix_v653.py` (12 tests) and adjusted pre-existing tests whose expectations the fixes intentionally changed (e.g. CLI failure paths now exit non-zero). Key mechanisms:

- **Windows config-lock liveness probe (B1)**: `config.py::_is_process_alive()` uses `OpenProcess` + `GetExitCodeProcess` via `ctypes` instead of `os.kill(pid, 0)`, which on Windows self-delivers `Ctrl+C` to the waiting process.
- **Corrupt-config recovery (B3)**: `save()` tolerates a corrupt/out-of-range disk file — it logs, rewrites from in-memory state, and returns normally instead of bricking every subsequent save.
- **Desktop preset compatibility (B2)**: the path-collection dialog reads preset attributes with a fallback chain (`attribute`, then `model_dump()` key) so presets work with Pydantic profile models.
- **Case-only rename (B6)**: `FileOps.rename_file` and batch rename skip the "target exists" conflict when `normcase()` proves the target is the same file under a different case.
- **Null-tolerant settings (B7)**: `update_global_settings` drops `None` values before validation, so partial payloads no longer 500; the frontend also guards `NaN` inputs.
- **gitignore/tree parity (B8)**: the tree walker passes `is_dir` to the ignore matcher so directory-only rules like `build/` apply in the file tree exactly as they do in search.
- **Case-faithful excludes (B9)**: five call sites stopped lowercasing exclude patterns; POSIX now honors case, Windows keeps the filesystem's case-insensitive behavior.
- **CLI exit codes (B14)**: `cmd_*` handlers return booleans and `main()` exits 1 on failure; existing CLI tests were updated to assert `SystemExit(1)`.
- **Search-size alignment (A4/B11)**: CLI and MCP search read the project's `max_search_size_mb` (fallback 10) instead of the module default 5; WS search results are `norm_path`-normalized so staging cannot double-register a path.
- **Event-loop safety (B17)**: MCP `search_files` runs the blocking generator via `asyncio.to_thread`; desktop tool execution moved to a background thread with results marshalled back through `root.after`.
- **WS 3.10 compatibility (B4)**: backpressure catches `concurrent.futures.TimeoutError` in addition to the builtin `TimeoutError`.
- **CORS preflight (B5)**: the token middleware passes `OPTIONS` through so browser preflights reach the CORS layer.

Verification result: `800 passed` (788 baseline + 12 new), `ruff check .` clean, packaging count guard updated to 800.

Run on Windows with a writable temporary directory when needed:

```powershell
$env:TEMP = "E:\VScode\file_search\.pytest_tmp"
$env:TMP = $env:TEMP
pytest -q
ruff check .
python -m build --no-isolation
```

## 10. Known Limits and Next Engineering Work

- JSON configuration is local-process coordination, not a multi-user database.
- Route handlers still contain application orchestration that should move to services (Phase 2).
- Frontend source contracts do not replace Playwright E2E coverage.
- Tool output and search are bounded but can still consume I/O on very large local workspaces.
- Token counts are heuristic and context selection is deterministic/manual, not semantic ranking.
- Windows config-lock probing requires the lock holder to be a local process; remote-process liveness cannot be probed with the Win32 API and is treated conservatively.
- The Web progress tracker is process-internal; multi-worker deployments are unsupported (see README deployment note).

See [CURRENT_ENGINEERING_PLAN.md](CURRENT_ENGINEERING_PLAN.md) for delivery phases and [ROADMAP.md](ROADMAP.md) for the prioritized feature list.
