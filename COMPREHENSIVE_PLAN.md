# FileCortex v6.3.0 Comprehensive Development Plan

> Refresh 2026-05-09
> Latest validated baseline: **`221 passed`** (`python -m pytest`)
> Scope of this refresh:
> 1. Complete code review, bug fix, and test expansion pass.
> 2. Fix all 3 previously failing tests.
> 3. Add 30 new regression tests covering edge cases.
> 4. Unify version numbering across all surfaces.
> 5. Complete frontend audit, 12 bug fixes, layout improvements.

---

## 0. Current Reality Check

### 0.1 What the project is today

FileCortex is a usable lightweight system with four delivery surfaces:

- Desktop GUI: `file_search.py` (1923 LOC)
- Web API/UI: `web_app.py` + `routers/` + `templates/` + `static/`
- CLI: `fctx.py` (134 LOC)
- MCP-facing bridge: `mcp_server.py` (312 LOC)

The shared kernel is `file_cortex_core/` (9 modules + gui/ submodule).

### 0.2 Verified baseline (2026-05-08)

- **Test suite**: `221 passed, 0 failed` (up from 188 passed / 3 failed)
- **Static lint**: All critical errors resolved. Only E501 (line length in test files) remains.
- **Version**: Unified to `v6.3.0` across `pyproject.toml`, `web_app.py`, `file_search.py`, `templates/index.html`

### 0.3 Issues found and fixed in this review

| ID | Category | File | Description | Status |
|----|----------|------|-------------|--------|
| FIX-1 | Test Bug | `tests/test_dm_config.py` | `test_dm_group_management` used stale dict snapshot after mutation | **Fixed** |
| FIX-2 | Test Bug | `tests/test_frontend_contract.py` | `summarySearchState` ID never existed in HTML | **Fixed** |
| FIX-3 | Missing Validation | `config.py:476` | `update_custom_tools` accepted non-dict without error | **Fixed** |
| FIX-4 | Undefined Name | `routers/http_routes.py` | `DataManager` used in type hints but not imported | **Fixed** |
| FIX-5 | Undefined Name | `routers/ws_routes.py` | `DataManager` used but not imported | **Fixed** |
| FIX-6 | Undefined Name | `mcp_server.py` | `logger` used but not imported | **Fixed** |
| FIX-7 | Runtime Bug | `mcp_server.py:211` | `root_dir` referenced instead of `root` variable | **Fixed** |
| FIX-8 | Unused Import | `config.py` | `import copy` was unused | **Fixed** |
| FIX-9 | Unused Import | `file_search.py` | `import re` was unused | **Fixed** |
| FIX-10 | Unused Import | `format_utils.py` | `from typing import Any` and `logger` were unused | **Fixed** |
| FIX-11 | Unused Import | `gui/duplicate_finder.py` | `FileUtils` was imported but unused | **Fixed** |
| FIX-12 | Style | `format_utils.py` | `elif` after `return` (RET505) | **Fixed** |
| FIX-13 | Style | `fctx.py` | `elif` after `return` (RET505) | **Fixed** |
| FIX-14 | Style | `actions.py` | Unnecessary `else` after `return` (RET505) | **Fixed** |
| FIX-15 | Style | `mcp_server.py` | Unnecessary assignment before return (RET504) | **Fixed** |
| FIX-16 | Style | Multiple | Import sorting (I001) across 8 files | **Fixed** |
| FIX-17 | Style | Multiple | Trailing whitespace/blank line whitespace (W291/W293) | **Fixed** |
| FIX-18 | Version Mismatch | Multiple | `v6.2.0` in pyproject.toml, web_app, file_search, index.html | **Fixed to v6.3.0** |

### 0.4 Architecture strengths confirmed

| Strength | Grade | Evidence |
|----------|-------|----------|
| Separation of Concerns | A | Core fully decoupled from UI; routers split into http/ws/services/schemas |
| Thread Safety | A | RLock singleton, atomic persistence with temp+replace |
| Security Defense-in-Depth | A- | PathValidator, input validation, timeout kill, UNC blocking |
| API Contract Consistency | B+ | Pydantic V2 models with field validation |
| Atomic Persistence | A | NamedTemporaryFile + os.replace with Windows retry |
| Multi-Entry Point | A | 4 interfaces sharing one core |
| Frontend Modularization | B+ | ES6 modules (main/state/api/ui) replace monolithic app.js |

### 0.5 Remaining architecture concerns (deferred to v7.0)

| Concern | Priority | Notes |
|---------|----------|-------|
| Desktop GUI still monolithic (1923 LOC) | P1 | Needs controller/view extraction |
| DataManager singleton used everywhere | P2 | Service locator anti-pattern |
| ACTIVE_PROCESSES at module scope | P2 | Needs dedicated runtime service |
| No rate limiting on API endpoints | P2 | Security hardening |
| CDN JS without SRI hashes | P3 | `templates/index.html` |

---

## 1. Complete Bug Manifest (All Resolved)

### 1.1 Bugs fixed in this session

See table in Section 0.3 above. All 18 issues resolved.

### 1.2 Previously fixed bugs (confirmed working)

| ID | Description | Verification |
|----|-------------|-------------|
| BUG-C1 | `ntpath` not imported in security.py | `ruff check` clean, 23 security tests pass |
| BUG-C2 | `is_safe` uses resolve() for non-existent paths | Fixed with abspath-based logic |
| BUG-C3 | Note/Tag path key mismatch | All note/tag tests pass |
| BUG-H1 | Missing exception chains (B904) | All routers use `from e` |
| BUG-M3 | `format_size` negative values | Returns "0 B" for negative input |
| BUG-L2 | `read_text_smart` fallback ignores max_bytes | Fixed in earlier refresh |

---

## 2. Test Coverage Matrix (221 Tests)

### 2.1 Coverage by module

| Module | Tests | Coverage Area |
|--------|-------|---------------|
| `config.py` (DataManager) | 15 | Singleton, persistence, groups, tags, notes, settings, tools validation, recent cap |
| `security.py` (PathValidator) | 23 | Path matrix (15 cases), UNC, sensitive dirs, injection, concurrency, edge cases |
| `search.py` (SearchWorker) | 25 | Mode matrix (16 combos), tags, gitignore, content mode, max results, interruption |
| `file_io.py` (FileUtils) | 12 | Binary detection, read_text_smart, gitignore, metadata, language tags |
| `format_utils.py` (FormatUtils) | 10 | Size formatting, number formatting, datetime, tokens, CJK, language tags |
| `context.py` (ContextFormatter) | 6 | Markdown, XML, CDATA escaping, blueprint, noise reduction |
| `actions.py` (FileOps/ActionBridge) | 18 | CRUD, rename, move, delete, archive, batch ops, categorization, execution |
| `duplicate.py` (DuplicateWorker) | 2 | Duplicate detection with excludes, hash cancellation |
| `web_api` (HTTP endpoints) | 30+ | CRUD, auth, CORS, settings, staging, favorites, archives, batch ops |
| `web_api` (WebSocket) | 5 | Search protocol, auth, parameter matrix, case-sensitive |
| `frontend_contract` | 4 | HTML elements, JS/CSS assets, desktop GUI structure |
| `mcp_server` | 3 | MCP tool registration, context generation, blueprint |
| `integration` | 10 | Encoding resilience, rollback, duplicate, full flow, path collection |
| **additional_coverage** | **30** | **New: search edge cases, file I/O edge cases, path validator, file ops, noise reducer, format utils, config edge cases** |
| **Total** | **221** | |

### 2.2 New tests added (test_additional_coverage.py)

| # | Test Name | Module | Validates |
|---|-----------|--------|-----------|
| 1 | test_search_content_mode_empty_file | search | Empty files don't crash content search |
| 2 | test_search_regex_mode_with_tags | search | Regex + positive/negative tags |
| 3 | test_search_smart_multi_keyword | search | Smart mode requires all keywords |
| 4 | test_search_max_results_enforcement | search | max_results limit respected |
| 5 | test_search_empty_query_returns_nothing | search | Empty query returns nothing |
| 6 | test_is_binary_empty_file | file_io | Empty files not classified as binary |
| 7 | test_is_binary_nonexistent | file_io | Non-existent files don't crash |
| 8 | test_is_binary_known_text_extensions | file_io | Text extensions short-circuit |
| 9 | test_read_text_smart_with_max_bytes | file_io | max_bytes respected |
| 10 | test_get_metadata_nonexistent | file_io | Returns defaults for missing files |
| 11 | test_get_language_tag_unknown | file_io | Unknown extensions return empty |
| 12 | test_should_ignore_git_spec | file_io | Git spec matching for nested paths |
| 13 | test_norm_path_with_dots | security | . and .. segments resolved |
| 14 | test_is_safe_same_path | security | Path safe against itself |
| 15 | test_is_safe_empty_root | security | Empty root returns False |
| 16 | test_validate_project_root_drive | security | Cannot register root drive |
| 17 | test_rename_rejects_traversal | actions | Path separators rejected in names |
| 18 | test_create_rejects_dotdot | actions | .. names rejected |
| 19 | test_delete_file_and_dir | actions | Both files and directories |
| 20 | test_archive_preserves_structure | actions | ZIP preserves directory structure |
| 21 | test_clean_normal_lines | context | Normal lines pass through |
| 22 | test_clean_truncates_long_lines | context | Lines >500 chars truncated |
| 23 | test_clean_detects_base64 | context | Base64-like content filtered |
| 24 | test_collect_paths_absolute_mode | format_utils | Absolute mode returns full paths |
| 25 | test_estimate_tokens_cjk_heavy | format_utils | CJK text has positive token estimate |
| 26 | test_update_custom_tools_rejects_non_dict | config | Non-dict input raises ValueError |
| 27 | test_add_note_roundtrip | config | Notes survive save/load |
| 28 | test_add_and_remove_tag | config | Tag add/remove lifecycle |
| 29 | test_resolve_project_root_empty | config | Empty path returns None |
| 30 | test_recent_projects_cap | config | Recent list capped at 15 |

---

## 3. Implementation Summary

### What was done

| Phase | Description | Result |
|-------|-------------|--------|
| **Phase 1** | Fix 3 failing tests | 191/191 passing |
| **Phase 2** | Fix ruff lint errors (imports, elif, unused imports, whitespace) | All critical errors resolved |
| **Phase 3** | Fix actual code bugs (DataManager import, logger import, root_dir variable) | 5 runtime/preventing bugs fixed |
| **Phase 4** | Version unification (6.2.0 → 6.3.0) | All surfaces consistent |
| **Phase 5** | Add 30 new comprehensive tests | 221/221 passing |
| **Phase 6** | Final verification and documentation | Complete |

### Files modified

| File | Changes |
|------|---------|
| `file_cortex_core/config.py` | Removed unused `copy` import, added validation in `update_custom_tools`, fixed long lines |
| `file_cortex_core/format_utils.py` | Removed unused imports, fixed `elif` after `return` |
| `file_cortex_core/actions.py` | Fixed unnecessary `else` after `return`, import sorting |
| `file_cortex_core/search.py` | Whitespace cleanup |
| `file_cortex_core/context.py` | Whitespace cleanup |
| `file_cortex_core/gui/duplicate_finder.py` | Removed unused `FileUtils` import |
| `file_cortex_core/__init__.py` | Import sorting |
| `file_search.py` | Removed unused `re` import, version update |
| `routers/http_routes.py` | Added `DataManager` import, import sorting |
| `routers/ws_routes.py` | Added `DataManager` import, import sorting |
| `routers/common.py` | Import sorting |
| `mcp_server.py` | Added `logger` import, fixed `root_dir` → `root`, removed unnecessary assignment |
| `fctx.py` | Fixed `elif` after `return` |
| `pyproject.toml` | Version 6.2.0 → 6.3.0 |
| `web_app.py` | Version 6.2.0 → 6.3.0 |
| `templates/index.html` | Version 6.2.0 → 6.3.0 |
| `tests/test_dm_config.py` | Fixed stale snapshot in `test_dm_group_management` |
| `tests/test_frontend_contract.py` | Removed non-existent `summarySearchState` ID |
| `tests/test_additional_coverage.py` | **New file**: 30 additional edge case tests |
| Various test files | Whitespace cleanup, import sorting |

---

## 4. Verification Checklist

- [x] `python -m pytest` returns 221 passed, 0 failed
- [x] `ruff check . --select E,F,I001` returns 0 critical errors
- [x] All version surfaces unified to v6.3.0
- [x] `update_custom_tools` validates input type
- [x] `DataManager` properly imported in all router modules
- [x] `logger` properly imported in `mcp_server.py`
- [x] `mcp_server.get_project_blueprint` uses correct variable
- [x] All note/tag operations survive normalization correctly
- [x] Binary files correctly skipped in context generation
- [x] Config persistence survives process restart (tested via save/load symmetry)

---

## 5. Roadmap (v7.0+)

### Short-term (v6.3.x maintenance)

1. **Desktop GUI decomposition**: Extract controller logic from `file_search.py` into separate modules
2. **Rate limiting middleware**: Add basic request throttling to FastAPI app
3. **SRI hashes for CDN resources**: Add integrity attributes to CDN script/link tags
4. **Type checking**: Add `mypy` to CI pipeline

### Medium-term (v7.0)

1. **Plugin system**: Define standard Hook interfaces for search backends and export formatters
2. **Repository indexing**: Persistent index for instant file search
3. **Git integration**: Diff context and blame annotations in AI export

### Long-term (v8.0+)

1. **Local LLM integration**: Codebase summarization with Ollama/llama.cpp
2. **Semantic search**: Embedding-based file similarity
3. **Cloud sync**: Cross-device configuration sync
