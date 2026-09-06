# FileCortex Technical Guide

> Version: 6.6.0 | Updated: 2026-09-06 | Verification baseline: 846 passed, Ruff 0 errors

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

`PathValidator.validate_project()` rejects missing, file, system, sensitive, and Windows UNC roots — including the long-prefix UNC spelling `\\?\UNC\server\share`, which is checked *after* the `\\?\` strip and *again* after `resolve()` in case a symlink or SUBST drive resolves to a network location. `PathValidator.is_safe(target, root)` resolves paths before containment comparison, so an in-project symlink cannot authorize its external target; it applies the same double UNC check to targets. All network-path rejections happen **before** any `resolve()`/`exists()` call, because those calls themselves trigger SMB authentication with the server user's credentials.

Registration is the only path into `config.projects`. `DataManager.get_project_data_obj()` refuses empty keys, and every metadata-mutating endpoint must resolve `project_path` through `dm.resolve_project_root()` (i.e. an already-registered root) before containment checks — containment alone does not register, and nothing else may auto-register (v6.6.0).

Every path is checked twice where it matters:

1. The adapter checks the request path against a registered project root.
2. Core operations validate generated or resolved targets such as rename results, archive output, category destinations, copy destinations, and ZIP members.

Never replace this with `startswith()`, normalized-string comparison, or a frontend-only check.

### 3.2 Web Trust Boundary

- The default listener is `127.0.0.1:8000`.
- Default CORS allows the standard loopback origins. Same-origin is decided by the Origin **host**: loopback hosts (`127.0.0.1`, `localhost`, `::1`) with any port, or an explicit `FCTX_ALLOWED_ORIGINS` entry. The client-controlled `Host` header is never used for this decision — a forged `Origin` + `Host` pair would otherwise pass as "same-origin".
- Binding outside loopback requires `FCTX_API_TOKEN`.
- When configured, HTTP uses `X-API-Token`; WebSocket uses the `token` query parameter; both are encoded to UTF-8 bytes before the constant-time comparison, so non-ASCII header values return 401 instead of raising `TypeError` inside `compare_digest(str, str)`.
- WebSocket auth failures `accept()` the handshake first, then `close(code=4001)`. Closing before accept makes the ASGI server answer the upgrade with a bare HTTP 403 and the custom code never reaches a browser.
- On shutdown, the FastAPI lifespan terminates any tool subprocesses still tracked by `ProcessManager`, so server exits and `--reload` restarts do not orphan detached children.
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
| `FCTX_EXEC_TIMEOUT` | environment | tool execution (HTTP, WS since 2.0 batch pending) | 300; invalid values fall back to 300 with a warning |
| `__version__` | `file_cortex_core.__version__` | Jinja template | dynamic (no hard-coded default anywhere) |

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
- CLI failure paths exiting with code 0: every `cmd_*` handler returns a boolean and `main()` calls `sys.exit(1)` on failure so scripts can detect errors programmatically. A missing/unknown subcommand prints help and exits **2**.
- Assuming `TimeoutError` is unified across Python versions: 3.10's `concurrent.futures.TimeoutError` is a distinct type, catch both.
- Letting a UI value `NaN` reach the backend as a setting: the API treats `null` as "no change" and the frontend guards NaN before sending.
- Catching `CancelledError` with `except Exception`: it derives from `BaseException` since Python 3.8, so the escape kills generators/worker threads before their DONE sentinel. Always list it explicitly around `future.result()` (v6.6.0).
- Trusting `as_completed()`/`wait()` to report cancelled futures: futures already in the `CANCELLED` state (as opposed to `CANCELLED_AND_NOTIFIED`) are silently treated as pending and block forever. Harvest `f.done()` explicitly before waiting, and prefer bounded `wait(timeout=...)` slices over bare `next(as_completed(...))` so cancellation stays responsive (v6.6.0).
- Passing raw strings to `hmac.compare_digest`: HTTP headers are latin-1 decoded and may contain non-ASCII, which raises `TypeError` (surfaces as a 500). Encode both sides to bytes first (v6.6.0).
- Closing a WebSocket before `accept()` when you want the client to see a custom close code: the server answers the upgrade with HTTP 403 and the code is lost. Accept, then close (v6.6.0).
- Deriving "same-origin" from `request.base_url`: it is built from the client-controlled `Host` header. Compare origins against loopback hosts or an explicit allowlist (v6.6.0).
- Treating path containment as authorization: `is_safe(file, project_path)` proves only geometry. Metadata-mutating endpoints must first resolve `project_path` to a registered root, or `get_project_data_obj` auto-registers arbitrary directories (v6.6.0).
- Free-form request fields: enum-ish values get `Literal` (`export_format` — `"XML"` silently fell through to markdown), numeric fields get `ge/le` bounds (`max_size_mb=-1` previously reached `f.read(-1)` and read whole files) (v6.6.0).
- Writing a rejected operation's side effects first: `extract_archive` used to `mkdir` the destination before validation, leaving empty dirs behind rejected archives. Validate, then mutate (v6.6.0).
- Frontend: reading server state after scheduling a debounced write — the reload races the 500ms debounce and resurrects stale data. Await `syncStagingToBackend.flushNow()` before refreshing (v6.6.0).
- Tk clipboard: `clipboard_append()` followed by immediate `destroy()` loses the content because Tk still owns the selection; call `update()` first (v6.6.0).
- `navigator.clipboard` without a Secure Context check: on plain-HTTP LAN deployments it is `undefined` and every copy action throws; fall back to `execCommand('copy')` (v6.6.0).

## 6. Search and Streaming

`PathMatcher` applies explicit positive/negative tags consistently in smart, exact, regex, and content flows. Smart mode derives path keywords from the query; other modes preserve their query semantics and apply only explicit tags.

Content search shares a thread pool but limits in-flight futures. Once the threshold is reached the iterator waits in 0.1s `wait(FIRST_COMPLETED)` slices, checking `stop_event` between slices, so a stuck executor delays cancellation by at most one slice (previously a bare `next(as_completed(...))` could block indefinitely). Task results are harvested defensively: `CancelledError` (a `BaseException` on 3.8+) is caught explicitly wherever `future.result()` is called, and the final drain first harvests `f.done()` futures — `as_completed()`/`wait()` never report futures already in the `CANCELLED` state — then bounded-waits for the rest. Every exit path (cancel, error, completion) still delivers the worker's DONE/ERROR sentinel to the UI queue.

Manual exclude patterns match both the file name and the rel-path in POSIX form (`str(rel_path).replace("\\", "/")`), so gitignore-style sub-path patterns like `docs/*` behave identically on Windows and POSIX. `FileUtils.get_metadata` returns the full key contract (`name/path/abs_path/type/size/size_fmt/mtime/mtime_fmt/ext`) on its failure fallback, so WS search frames built from vanished files cannot `KeyError`.

WebSocket search and tool execution use bounded async queues. Producer threads block while a slow client consumes data, instead of allocating an unbounded result list. Disconnect and error paths set stop signals and terminate registered tool processes; a search thread that crashes mid-scan now enqueues an explicit `{"status": "ERROR", "msg": ...}` frame before the final DONE, so clients never mistake a crash for a clean finish. Backpressure waits catch both the builtin `TimeoutError` (3.11+) and `concurrent.futures.TimeoutError` (3.10), so the 3.10 support tier behaves identically.

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

The suite has 846 tests across unit, integration, Web/API, CLI, MCP, security, packaging, file-operation, and frontend contract layers.

Important regression families:

| Area | Representative coverage |
|---|---|
| containment | external context paths, symlink paths, rename traversal, archive targets, UNC long-prefix forms |
| persistence | snapshot isolation, independent instance merge, schema ranges, corrupt-config backup |
| file operations | copy rollback, ZIP slip, ZIP resource limits, conflict behavior, rejected-extract dir hygiene |
| context | CDATA, XML parsing, truncation, noise reducer |
| search | four modes, tags, cancellation, shared-pool recovery, cancelled-future drain, backpressure stop responsiveness |
| frontend | preview/search race guards, staging sync, progress contract, clipboard fallback |
| packaging | entry modules, runtime assets, versions, docs test-count consistency |
| v6.5.3 fixes | Windows lock probe, preset Pydantic compat, corrupt-config recovery, case-only rename, null-setting tolerance, gitignore directory rules, case-faithful excludes, ZIP slash names, CLI exit codes, search-size alignment, WS 3.10 backpressure, threaded desktop tools |
| v6.6.0 fixes | UNC long-prefix bypass, note/tag registration gate, MCP transport wiring, POSIX process-group detach, corrupt-config backup, search CancelledError/cancelled-future drain, backpressure stop responsiveness, sub-path excludes, metadata fallback contract, WS ERROR frame, duplicate cancel sentinel, WS 4001 delivery, origin/Host hardening, byte-wise token compare, lifespan process cleanup, extract UNC source + dir hygiene, schema Literal/bounds, CLI exit-2, literal rename replacement, timeout-env fallback |

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

### 9.2 v6.6.0 Review-Driven Hardening Archive (process and results)

The v6.6.0 round started from a four-way parallel deep review (core / web+entries / frontend+GUI / test suite) whose findings were re-verified by hand against the source before any fix. Every fix landed with an anchored regression test in `tests/test_v660_review_fixes.py` (46 tests); four pre-existing tests were updated because the fixes intentionally changed observable behavior (WS close-code delivery, CLI no-subcommand exit code, bulk bar visibility contract). Full findings, deferred items, and the batched forward plan live in `docs/CODE_REVIEW_V660.md` and `docs/IMPLEMENTATION_PLAN_V660.md`. Key mechanisms:

- **UNC long-prefix bypass (P1)**: `security.py` now treats `UNC\server\share` (the `\\?\UNC\...` form after prefix stripping) as a network path in both `validate_project` and `is_safe`, and re-checks the resolved drive letter for `\\` — a symlink/SUBST chain that resolves onto a share is rejected too. All checks run before any `resolve()`/`exists()` that could touch SMB.
- **note/tag registration bypass (P1)**: `/api/project/note` and `/api/project/tag` resolve `project_path` through `get_valid_project_root` first. Previously containment alone plus `get_project_data_obj`'s create-if-missing semantics silently registered arbitrary directories (e.g. the system root) and opened them to every other endpoint.
- **MCP transport wiring (P1)**: `main()` forwards `transport` to `FastMCP.run()`; the legacy `--transport http` alias maps to `streamable-http`, and `sse`/`streamable-http` are accepted directly. HTTP mode is actually usable now.
- **POSIX process-group self-kill (P1)**: `execute_tool`'s `Popen` sets `start_new_session=True` off-Windows so the timeout path's `killpg` can no longer SIGTERM the server itself.
- **Corrupt-config backup (P1)**: `save()` copies a corrupt `config.json` to `config.json.corrupt-<timestamp>` before rewriting from in-memory state — no more unrecoverable data loss.
- **Search future lifecycle (P2)**: `CancelledError` is caught explicitly at all three `f.result()` sites and in `SearchWorker.run`; the final drain harvests `f.done()` futures first (as_completed/wait never report the CANCELLED state) and bounded-waits in 0.2s slices with stop checks; the backpressure wait runs in 0.1s slices. A stuck or reinitialized pool can no longer hang or crash the generator before its DONE sentinel.
- **Exclude/metadata contract (P2)**: manual sub-path patterns are matched against POSIX-separated rel paths (Windows parity); `get_metadata`'s failure fallback carries the full success-branch key contract, eliminating the `res_dict["path"]` KeyError that used to crash WS search mid-stream and get swallowed as DONE.
- **WS protocol (P2)**: search-thread crashes enqueue an ERROR frame before DONE; auth failures accept-then-close(4001) so browsers see the real code; token comparisons encode to bytes first.
- **Origin hardening (P2)**: same-origin is decided by the Origin host (loopback set or explicit allowlist), never the Host-derived base URL.
- **Lifecycle & bounds (P2/P3)**: app lifespan terminates tracked subprocesses on shutdown; `FCTX_EXEC_TIMEOUT` parses once with a 300s fallback and skipped paths are reported in `/api/actions/execute` results; schemas gained `Literal`/`ge/le` bounds (`export_format`, tag length, rename count, `SearchQuery` limits); `read_text_smart` treats non-positive limits as "read nothing"; `get_project_data_obj` rejects empty keys; extract validates before `mkdir` and blocks UNC sources in core (before resolve/exists) and in the Web route; `DuplicateWorker` always delivers its DONE sentinel; the GUI duplicate finder stops its worker on ERROR and cancels its poll timer; batch-rename simple mode escapes replacement backslashes via `build_literal_substitution()`; the CLI exits 2 on missing/unknown subcommands; MCP normalizes `fmt` case and reports its 50-entry truncation; config-lock breaking re-reads the owner before unlink (TOCTOU) and treats `OpenProcess` ACCESS_DENIED as alive.
- **Frontend/desktop races (P1/P2)**: categorize flushes debounced staging persistence before reloading the project; empty queries are rejected before bumping `searchGeneration` (no more wedged search UI); select-all merges DOM nodes with the full virtual-list result set; clipboard actions fall back to `execCommand('copy')` off Secure Contexts; tool execution has a re-entrancy guard; the desktop preview switches behind an unsaved-changes guard; the light theme's close buttons are visible again.

Verification result: `846 passed` (800 baseline + 46 new), `ruff check .` clean, packaging count guard updated to 846. Deferred findings (WS tool-stream timeout, `stream_tool` grandchild processes, save-storm debouncing, desktop main-thread IO, unified route authorization dependency) are scheduled in `docs/IMPLEMENTATION_PLAN_V660.md` §4 batches 2.0/2.1.

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
- Route handlers still contain application orchestration that should move to services; the per-route registered-root + containment checks should converge into a single authorization dependency (Phase 2, batch 2.1).
- `DataManager` still performs a full lock-read-merge-write cycle per small mutation; dirty-flag + debounced saves are scheduled (Phase 2, batch 2.0).
- The WebSocket tool stream has no execution timeout (the HTTP path enforces `FCTX_EXEC_TIMEOUT`); parity is scheduled (Phase 2, batch 2.0).
- `stream_tool` (shell mode) can leak shell grandchild processes holding the output pipe on some platforms; Job Object / process-group handling is scheduled (Phase 2, batch 2.0).
- Desktop Tkinter still performs some synchronous file I/O on the UI thread (large staging exports, staging-filter traces); backgrounding is scheduled (Phase 2, batch 2.0).
- Frontend source contracts do not replace Playwright E2E coverage (Phase 2).
- Tool output and search are bounded but can still consume I/O on very large local workspaces.
- Token counts are heuristic and context selection is deterministic/manual, not semantic ranking.
- Windows config-lock probing requires the lock holder to be a local process; remote-process liveness cannot be probed with the Win32 API and is treated conservatively.
- The Web progress tracker is process-internal; multi-worker deployments are unsupported (see README deployment note).
- Search regex mode matches path names only; a combined regex-content semantic is a documented Phase 3 decision.

See [CURRENT_ENGINEERING_PLAN.md](CURRENT_ENGINEERING_PLAN.md) for delivery phases, [ROADMAP.md](ROADMAP.md) for the prioritized feature list, [docs/IMPLEMENTATION_PLAN_V660.md](docs/IMPLEMENTATION_PLAN_V660.md) for the batched execution plan, and [docs/CODE_REVIEW_V660.md](docs/CODE_REVIEW_V660.md) for the complete findings ledger.
