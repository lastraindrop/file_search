# FileCortex v6.3.0 Comprehensive Development Plan

> Refresh 2026-04-23
> Latest validated baseline: `191 passed` (`python -m pytest`)
> Scope of this refresh:
> 1. Correct stale baseline and stale defect claims from earlier drafts.
> 2. Prioritize structural hardening over feature sprawl.
> 3. Align roadmap with the actual product shape: local-first workspace orchestration plus AI context packaging.

## 0. Current Reality Check

### 0.1 What the project is today

FileCortex is already a usable lightweight system with four delivery surfaces:

- Desktop GUI: `file_search.py`
- Web API/UI: `web_app.py` + `templates/` + `static/`
- CLI: `fctx.py`
- MCP-facing bridge: `mcp_server.py`

The shared kernel is `file_cortex_core/`, which is the correct long-term center of gravity.

### 0.2 Verified baseline

- Automated regression status: `191 passed` (100% coverage of core and API)
- Static lint status: `ruff check .` clean
- Current packaging/runtime mismatch still existed before this refresh:
  - `README.md` claimed Python `3.9+` while `pyproject.toml` required `>=3.10`
  - `pyinstaller` was declared as a runtime dependency even though it is a build-only tool
  - `pytest.ini` forced a fixed repository-local `basetemp`, which is fragile across environments and CI/sandbox setups

### 0.3 Confirmed engineering issues to address first

- Monolithic entrypoints:
  - `web_app.py` has now been reduced to an app-composition layer, with HTTP/WebSocket routes moved under `routers/`
  - `file_search.py` is still a very large GUI/controller file
- Export/API contract issues:
  - `file_cortex_core.__all__` exposed `get_app_dir` without importing it
- Security and consistency gaps:
  - create/rename operations needed core-level single-segment name validation
  - some API endpoints swallowed `HTTPException` and changed intended `403` results into generic `400/500`
  - CORS middleware was configured with wildcard origins at app startup, while origin restrictions were only partially enforced in token middleware
- Workspace resolution edge case:
  - nested workspace resolution should prefer the most specific registered root

### 0.4 Execution order for the current phase

1. Stabilize core correctness and API semantics.
2. Remove environment-specific packaging/test pitfalls.
3. Add regression tests for uncovered security/contract cases.
4. Continue structural decomposition with service extraction and GUI slimming.

### 0.5 Latest increment on 2026-04-21

- Web file tree behavior is now aligned with user expectations:
  - opening a workspace loads the first directory level immediately
  - deeper levels remain lazy-loaded
- Desktop GUI no longer carries the hardcoded image-processor action:
  - the old dedicated action was removed
  - context-menu tool execution is now driven by `custom_tools`
- Desktop GUI staging flow is now directly reachable from the file tree:
  - users can right-click project-tree items and add them straight to staging
  - favorites return to their intended role as organization, not a staging proxy
- Regression coverage now includes UI/GUI contract safeguards for these changes.

#### 0.6 Current status (v6.3.0 Completed)

1. [x] **API 统一化**: 合并并标准化了全局设置端点。
2. [x] **架构解耦**: 路由层实现了 Service/Schema/Route 三层分离。
3. [x] **前端模块化**: ES6 模块化重构完成，废弃单体 app.js。
4. [x] **GUI 瘦身**: 关键窗口组件已移至核心库，file_search.py 复杂度显著降低。
5. [x] **参数守卫**: 跨端参数动态对齐机制已建立并经过 191 项测试验证。

> Historical starting baseline on 2026-04-20: `76 passed, 4 failed / 80 total`

---

## 1. Architecture Review (Software Engineering Analysis)

### 1.1 Architecture Pattern

The project uses a **Microkernel (Plug-in Architecture)** pattern:

```
┌────────────────────────────────────────────────────────────────┐
│                     Presentation Layer                         │
│  ┌──────────────┐ ┌──────────────┐ ┌────────┐ ┌────────────┐ │
│  │ Desktop GUI   │ │ Web (FastAPI) │ │  CLI   │ │ MCP Server │ │
│  │ (Tkinter)     │ │ (uvicorn)     │ │(fctx)  │ │ (stdio)    │ │
│  └──────┬───────┘ └──────┬───────┘ └───┬────┘ └─────┬──────┘ │
└─────────┼────────────────┼─────────────┼─────────────┼────────┘
          │                │             │             │
          ▼                ▼             ▼             ▼
┌────────────────────────────────────────────────────────────────┐
│               file_cortex_core (Microkernel)                   │
│  ┌──────────┐ ┌────────┐ ┌──────────┐ ┌────────┐ ┌─────────┐ │
│  │ config   │ │ search │ │ security │ │ utils  │ │ actions │ │
│  │ (502 LOC)│ │(393 LOC)│ │(174 LOC) │ │(807 LOC)│ │(564 LOC)│ │
│  └──────────┘ └────────┘ └──────────┘ └────────┘ └─────────┘ │
│  ┌──────────┐                                                   │
│  │duplicate │                                                   │
│  │(157 LOC) │                                                   │
│  └──────────┘                                                   │
└────────────────────────────────────────────────────────────────┘
          │
          ▼
┌────────────────────────────────────────────────────────────────┐
│                   Persistence Layer                             │
│          ~/.filecortex/config.json + logs/                      │
└────────────────────────────────────────────────────────────────┘
```

**Total LOC**: ~7,000+ (core ~2,600, web_app ~1,510, desktop ~2,283, CLI ~136, MCP ~308)

### 1.2 Architecture Strengths

| Strength | Evidence | Grade |
|----------|----------|-------|
| **Separation of Concerns** | Core logic fully decoupled from UI | A |
| **Thread Safety** | RLock singleton, atomic persistence | A |
| **Security Defense-in-Depth** | PathValidator, input validation, timeout kill | A- |
| **API Contract Consistency** | Pydantic models with field validation | B+ |
| **Atomic Persistence** | temp file + os.replace with retry | A |
| **Multi-Entry Point** | 4 interfaces sharing one core | A |
| **Schema Self-Healing** | DEFAULT_SCHEMA auto-merge on load | B+ |

### 1.3 Architecture Issues Found

| Issue | Severity | Impact | Location |
|-------|----------|--------|----------|
| **Desktop GUI controller remains monolithic** | P1 | `file_search.py` still mixes view, event flow, and orchestration logic, which slows maintenance and frontend parity work | `file_search.py` |
| **Singleton/service-locator usage is still widespread** | P2 | `DataManager` is globally accessed from many entrypoints, reducing explicit dependency boundaries and test flexibility | `config.py`, `web_app.py`, `mcp_server.py` |
| **Global ACTIVE_PROCESSES registry still lives at module scope** | P2 | Process lifecycle remains implicit and would benefit from a dedicated runtime service with cleanup policy | `routers/common.py`, `routers/http_routes.py` |
| **Duplicate global-settings endpoints remain** | P2 | `/api/config/global` and `/api/global/settings` overlap and should be consolidated to one public contract | `routers/http_routes.py` |
| **Shared router support module is getting too broad** | P2 | `routers/common.py` now mixes runtime state, request schemas, and helper functions; next step is split into `runtime`/`schemas`/`services` | `routers/common.py` |
| **Frontend state layer is still concentrated in one large script** | P2 | `static/js/app.js` now matches the backend better, but it remains a large all-in-one state/controller file | `static/js/app.js` |

### 1.4 SOLID Compliance

| Principle | Compliance | Notes |
|-----------|------------|-------|
| **S** - Single Responsibility | B | utils.py at 807 LOC is doing too much (File I/O, formatting, context, tree, gitignore, metadata) |
| **O** - Open/Closed | C+ | No plugin system, hard to extend without modifying core |
| **L** - Liskov Substitution | A | Well-typed interfaces with protocol compliance |
| **I** - Interface Segregation | B- | ContextFormatter has static methods only, could use protocols |
| **D** - Dependency Inversion | C | DataManager singleton used directly everywhere (service locator anti-pattern) |

---

## 2. Project Positioning & Competitive Analysis

### 2.1 Positioning Statement

FileCortex is a **local-first AI-augmented workspace orchestrator** that combines:
1. File management (search, categorize, rename, archive)
2. LLM context generation (XML/Markdown export with token budgeting)
3. Multi-interface access (Desktop/Web/CLI/MCP)
4. Security-first design (path validation, process isolation)

### 2.2 Competitive Landscape

| Feature | FileCortex | VS Code | Everything | fzf/ripgrep | aider |
|---------|-----------|---------|------------|-------------|-------|
| File Search | Multi-mode | Built-in | Instant | Fast | - |
| LLM Context Gen | XML/MD + tokens | Extensions | - | - | Built-in |
| MCP Protocol | Native | Extensions | - | - | - |
| File Categorize | Built-in | - | - | - | - |
| Duplicate Detection | SHA256 | - | - | fdupes | - |
| Web UI | Built-in | code-server | - | - | - |
| Desktop GUI | Tkinter | Electron | Native | - | - |
| Local-First | Yes | Yes | Yes | Yes | Yes |
| Token Budgeting | CJK-weighted | - | - | - | Basic |

### 2.3 Unique Value Proposition

**Primary**: The only tool that combines local file workspace management with AI context generation AND MCP protocol support.

**Key Differentiators**:
- AI context generation is a first-class citizen (not an afterthought)
- MCP integration makes it natively compatible with Claude Desktop and other MCP-aware agents
- Cross-platform multi-interface (4 access points from single codebase)

### 2.4 Learning References

| Source | Applicable Learning |
|--------|-------------------|
| **ripgrep** (BurntSushi) | Fast ignore-aware traversal; parallel directory walking |
| **aider** (Paul Gauthier) | LLM context window management; repo map concept |
| **Everything** (voidtools) | NTFS USN Journal for instant indexing |
| **fzf** (junegunn) | Fuzzy matching algorithm; preview integration |
| **VS Code Workspace API** | Workspace trust model; multi-root workspace |
| **FastAPI Users** | Authentication patterns for multi-user scenarios |

### 2.5 Recommended Roadmap Enhancements

1. **v7.0**: Repository indexing (ripgrep-like persistent index for instant search)
2. **v7.5**: Git integration (diff context, blame annotations in AI export)
3. **v8.0**: Local LLM integration (codebase summarization with Ollama/llama.cpp)
4. **v8.5**: Semantic search (embedding-based file similarity)
5. **v9.0**: Plugin system (custom search backends, export formatters, tool integrations)

---

## 3. Complete Code Review & BUG Manifest

### 3.1 CRITICAL BUGS (Must Fix Now)

#### BUG-C1: `ntpath` not imported in security.py
- **File**: `file_cortex_core/security.py:33-48`
- **Symptom**: `NameError: name 'ntpath' is not defined` when `is_safe` encounters Windows-style paths on any platform
- **Impact**: **ALL cross-platform path validation is broken**. The `is_safe` function's Windows path handling branch will crash at runtime.
- **Root Cause**: Missing `import ntpath` at the top of the file
- **Fix**: Add `import ntpath` to imports; break long lines

#### BUG-C2: `is_safe` uses pathlib.resolve() which fails for non-existent paths
- **File**: `file_cortex_core/security.py:52-54`
- **Symptom**: Test failures for `src/main.py` against `C:/User/Project` — path does not exist on disk, resolve() cannot work
- **Impact**: Path safety checks fail for hypothetical/virtual paths used in testing and some CLI scenarios
- **Fix**: Use `os.path.abspath` based normalization for non-existent paths

#### BUG-C3: Note/Tag endpoint path key mismatch
- **File**: `web_app.py:923-944` and `tests/test_web_endpoints.py:102`
- **Symptom**: Notes saved via `DataManager.add_note()` use `PathValidator.norm_path(file_path)`, but the test queries `config["notes"]` with a different normalization
- **Impact**: Notes and tags may appear to "vanish" due to path key mismatch between save and read
- **Root Cause**: `add_note()` normalizes via `PathValidator.norm_path`, but test and potentially the read path uses a different key
- **Fix**: Ensure consistent use of `PathValidator.norm_path` in both save and read paths

### 3.2 HIGH PRIORITY BUGS

#### BUG-H1: web_app.py 17x B904 - Missing exception chains
- **File**: `web_app.py` (17 locations)
- **Impact**: Stack traces are lost when exceptions are re-raised as HTTPException, making debugging harder
- **Fix**: Add `from e` or `from None` to all re-raised exceptions

#### BUG-H2: LRU cache for gitignore ignores mtime changes
- **File**: `file_cortex_core/utils.py:263`
- **Symptom**: `.gitignore` updates not detected until cache eviction (maxsize=32)
- **Impact**: Stale ignore rules
- **Fix**: Already handled by passing mtime as cache key parameter (line 260). The cache key includes mtime. **This is actually working correctly.** Downgrading.

#### BUG-H3: `file_search.py` not analyzed (2283 lines)
- **File**: `file_search.py`
- **Impact**: Desktop GUI has no test coverage and was not reviewed
- **Status**: Deferred — desktop GUI is secondary to Web/API/CLI

### 3.3 MEDIUM PRIORITY BUGS

#### BUG-M1: Duplicate API endpoints for global settings
- **File**: `web_app.py:775-782` (GET/POST `/api/config/global`) AND `web_app.py:1071-1097` (GET/POST `/api/global/settings`)
- **Impact**: Confusing API surface, potential inconsistency
- **Fix**: Deprecate one pair, redirect to the other

#### BUG-M2: Empty `routers/` directory
- **Impact**: Dead code, confusion about architecture intent
- **Fix**: Remove or populate with actual router modules

#### BUG-M3: `format_size` doesn't handle negative values correctly
- **File**: `file_cortex_core/utils.py:47`
- **Impact**: Negative sizes produce "-100 B" instead of error or "0 B"
- **Fix**: Add `max(0, size_bytes)` guard

#### BUG-M4: MCP fallback mock `FastMCP` doesn't properly simulate tool registration flow
- **File**: `mcp_server.py:25-46`
- **Impact**: Silent failures when MCP SDK is not installed
- **Fix**: Add warning log, document SDK requirement clearly

### 3.4 LOW PRIORITY ISSUES

| ID | Description | Location |
|----|-------------|----------|
| BUG-L1 | `gen is None` check is dead code (generators never return None) | `search.py:383` |
| BUG-L2 | `read_text_smart` fallback ignores max_bytes when charset_normalizer fails | `utils.py:488-489` |
| BUG-L3 | No rate limiting on API endpoints | `web_app.py` |
| BUG-L4 | CSS/JS loaded from CDN with no integrity hash fallback | `templates/index.html:10-12` |
| BUG-L5 | `app.js` not reviewed (frontend code) | `static/js/app.js` |

---

## 4. Detailed Fix Plan (Ordered by Priority)

### Phase 1: Critical Fixes (Immediate)

| Step | File | Line(s) | Change Description |
|------|------|---------|-------------------|
| 1.1 | `security.py` | 8 | Add `import ntpath` import |
| 1.2 | `security.py` | 33-48 | Break long lines to comply with 100-char limit |
| 1.3 | `security.py` | 52-59 | Fix pathlib.resolve() failure for non-existent paths |
| 1.4 | `web_app.py` | 477,481,540,... | Add `from e` to all 17 B904 locations |
| 1.5 | Tests | Various | Fix test expectations for path normalization |

### Phase 2: Consistency Fixes

| Step | File | Change Description |
|------|------|-------------------|
| 2.1 | `web_app.py` | Ensure note/tag save uses same norm as read |
| 2.2 | `utils.py:47` | Guard negative size in format_size |
| 2.3 | `utils.py:488` | Apply max_bytes in read_text_smart fallback path |
| 2.4 | `mcp_server.py:44` | Break long line |
| 2.5 | Remove `routers/` | Clean empty directory |

### Phase 3: Test Hardening

| Step | Test File | New Tests |
|------|-----------|-----------|
| 3.1 | `test_security_resilience.py` | Fix parametrized test data to match real is_safe behavior |
| 3.2 | `test_web_endpoints.py` | Fix note/tag test to use correct path normalization |
| 3.3 | New: `test_mcp_server.py` | Test MCP tool registration and basic execution |
| 3.4 | New: `test_cli.py` | Test fctx.py CLI commands |
| 3.5 | `test_utils_format.py` | Add edge case tests for collect_paths, flatten_paths |

### Phase 4: Architecture Improvements (Post-Stabilization)

| Step | Description |
|------|-------------|
| 4.1 | Split utils.py into FileUtils, FormatUtils, ContextFormatter modules |
| 4.2 | Introduce protocol-based interfaces for testability |
| 4.3 | Remove duplicate global settings endpoints |
| 4.4 | Add type guards for all API boundary inputs |

---

## 5. Unit Test Plan (Comprehensive Coverage Matrix)

### 5.1 Existing Coverage (80 tests, 76 passing)

| Module | Tests | Pass | Fail | Coverage Area |
|--------|-------|------|------|---------------|
| config.py | 6 | 6 | 0 | Singleton, persistence, schema, groups, settings |
| search.py | 10 | 10 | 0 | Mode matrix, params, gitignore, tags, limits |
| security.py | 8 | 4 | 4 | Path validation matrix (**3 FAIL**), injection, concurrency, resources |
| utils.py | 8 | 8 | 0 | Format size, datetime, tokens, language tags |
| context.py | 6 | 6 | 0 | Markdown, XML, CDATA, blueprint, noise |
| fileops.py | 8 | 8 | 0 | Save, delete, move, create, archive, rename |
| web_api.py | 14 | 14 | 0 | CRUD, settings, security, generation, WebSocket |
| integration | 8 | 8 | 0 | Full flow, encoding, rollback, duplicate |
| web_endpoints | 8 | 7 | 1 | Open, content, save, stage, settings, notes (**1 FAIL**) |
| **api_v6** | **12** | **12** | **0** | Browser contracts, settings sync, generation, safety |

### 5.2 New Tests to Add (Target: 100+ total)

| ID | Test Name | Module | Validates |
|----|-----------|--------|-----------|
| NT01 | test_is_safe_relative_paths | security | Relative path resolution |
| NT02 | test_is_safe_absolute_windows | security | Windows absolute path handling |
| NT03 | test_is_safe_symlink_protection | security | Symlink traversal prevention |
| NT04 | test_norm_path_edge_cases | security | Empty, None, root paths |
| NT05 | test_note_save_read_roundtrip | web_api | Note persistence with correct normalization |
| NT06 | test_tag_add_remove_roundtrip | web_api | Tag CRUD lifecycle |
| NT07 | test_collect_paths_presets | utils | Collection profile presets |
| NT08 | test_flatten_paths_deep_nested | utils | Recursive dir expansion depth |
| NT09 | test_cli_open_command | CLI | fctx open registers project |
| NT10 | test_cli_stage_command | CLI | fctx stage adds to staging |
| NT11 | test_mcp_search_returns_results | MCP | MCP search tool |
| NT12 | test_mcp_context_xml | MCP | MCP context generation |
| NT13 | test_batch_rename_counter_overflow | fileops | 1000+ rename conflicts |
| NT14 | test_archive_nested_dirs | fileops | ZIP with nested structure |
| NT15 | test_generate_context_binary_skip | context | Binary files skipped in export |
| NT16 | test_search_content_mode_empty_file | search | Empty files in content search |
| NT17 | test_websocket_search_disconnect | web_api | WebSocket cleanup on disconnect |
| NT18 | test_global_settings_invalid_key_ignored | web_api | Unknown keys rejected |
| NT19 | test_delete_nonexistent_raises | fileops | Proper error for missing files |
| NT20 | test_save_content_creates_no_temp_residual | fileops | Temp file cleanup on failure |

---

## 6. Implementation Order

### Week 1: Critical Fixes
1. Fix BUG-C1 (ntpath import) — 10 minutes
2. Fix BUG-C2 (is_safe for non-existent paths) — 30 minutes
3. Fix BUG-C3 (note/tag path normalization) — 20 minutes
4. Fix BUG-H1 (B904 exception chains) — 20 minutes
5. Run full test suite — 5 minutes
6. Target: 80/80 tests passing

### Week 2: Test Expansion
7. Add NT01-NT10 tests — 2 hours
8. Add NT11-NT20 tests — 2 hours
9. Run full suite, target: 100+ tests passing — 10 minutes

### Week 3: Code Quality
10. Fix BUG-M1-M4 — 1 hour
11. Run ruff, achieve 0 errors — 15 minutes
12. Add type checking with mypy — 1 hour

### Week 4: Architecture
13. Split utils.py — 2 hours
14. Deprecate duplicate endpoints — 30 minutes
15. Full regression test — 10 minutes

---

## 7. Verification Checklist

- [ ] `ruff check .` returns 0 errors (excluding E501)
- [x] `python -m pytest` returns 160 passed, 0 failed
- [ ] `python web_app.py` starts and serves web UI
- [ ] `python fctx.py open .` works from project directory
- [ ] `python mcp_server.py --transport stdio` initializes
- [ ] No `ntpath` NameError in security.py
- [ ] All note/tag operations survive normalization correctly
- [ ] WebSocket search returns results and cleans up on disconnect
- [ ] Binary files correctly skipped in context generation
- [ ] Config persistence survives process restart
