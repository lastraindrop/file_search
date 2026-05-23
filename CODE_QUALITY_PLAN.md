# Code Quality Audit & Remediation Plan

**Date:** 2026-05-24  
**Scope:** Full codebase — Python backend, JavaScript frontend, CSS, HTML  
**Standards:** Google Python Style Guide (GPG), ESLint recommended, WCAG 2.1 AA  

---

## Executive Summary

| Metric | Python Backend | JS Frontend | CSS | HTML |
|--------|---------------|-------------|-----|------|
| Files audited | 22 | 4 | 1 | 1 |
| Critical issues | 0 | 3 (XSS) | 1 (bug) | 0 |
| High issues | 42 | 6 | 2 | 0 |
| Medium issues | 25 | 8 | 5 | 4 |
| Low issues | 5 | 2 | 0 | 3 |

---

## P0 — CRITICAL (Must Fix Immediately)

### SEC-1: XSS via `marked.parse()` rendering untrusted HTML
- **File:** `static/js/main.js:414`
- **Risk:** File content containing `<script>` or malicious HTML executes in browser
- **Fix:** Add DOMPurify sanitizer or use `marked.setOptions({ sanitize: true })`

### SEC-2: XSS via unescaped `mtime_fmt` in innerHTML
- **File:** `static/js/ui.js:268`
- **Risk:** Server-returned `mtime_fmt` inserted directly into DOM
- **Fix:** Wrap with `escapeHtml(data.mtime_fmt)`

### SEC-3: XSS via unescaped `fileName` in tool execution modal
- **File:** `static/js/main.js:740`
- **Risk:** File paths containing HTML break out of template
- **Fix:** Wrap with `escapeHtml(fileName)`

### BUG-1: `.pulse-warning` CSS class referenced but never defined
- **File:** `static/js/main.js:958,955,945` references `.pulse-warning`
- **Fix:** Add `.pulse-warning` animation in style.css

### API-1: 11 API functions return Response instead of parsed JSON
- **File:** `static/js/api.js` — `saveProjectSettings`, `saveGlobalSettings`, `saveFileNote`, `archiveFiles`, `renameFile`, `deleteFiles`, `saveFileContent`, `terminateProcess`, `openInOs`, `toggleFavorite`, `manageTag`
- **Risk:** Callers may try to access `.data` on a Response object
- **Fix:** Return `await res.json()` or `null` for 204-style responses

### SOCK-1: WebSocket `onerror` silently resolves promise
- **File:** `static/js/main.js:806`
- **Risk:** Tool execution appears to succeed despite socket error
- **Fix:** Reject the promise or show error toast

---

## P1 — Python Backend (Google Python Style Guide)

### TYPE-1: Replace bare `dict`/`list`/`Queue` with parameterized generics (14 instances)

| File | Line | Current | Fix |
|------|------|---------|-----|
| `routers/schemas.py` | 119 | `dict \| None` | `dict[str, Any] \| None` |
| `routers/schemas.py` | 135 | `dict` | `dict[str, Any]` |
| `routers/schemas.py` | 142 | `dict` | `dict[str, Any]` |
| `routers/schemas.py` | 149 | `dict` | `dict[str, Any]` |
| `routers/schemas.py` | 155 | `dict` | `dict[str, Any]` |
| `file_cortex_core/config.py` | 514 | `dict` | `dict[str, Any]` |
| `file_cortex_core/config.py` | 522 | `dict` | `dict[str, Any]` |
| `file_cortex_core/config.py` | 590 | `dict` | `dict[str, Any]` |
| `file_cortex_core/gui/path_collection.py` | 19 | `dict` | `dict[str, Any]` |
| `routers/services.py` | 33 | `dict \| None` | `dict[str, Any] \| None` |
| `routers/ws_routes.py` | 67,159 | `asyncio.Queue` | `asyncio.Queue[dict[str, Any] \| str]` |
| `file_cortex_core/search.py` | 222 | `dict[Any, ...]` | `dict[Future, str]` |
| `file_cortex_core/file_io.py` | 26,266 | `object` | `threading.Event \| None` |
| `file_cortex_core/actions.py` | 176 | `tuple` | `tuple[type[BaseException], BaseException, TracebackType \| None]` |

### EXC-1: Replace 28 `except Exception` with specific exception types

Priority locations (I/O heavy, most likely to hide real bugs):
1. `file_cortex_core/file_io.py` — 7 instances → `OSError`, `UnicodeDecodeError`
2. `file_cortex_core/actions.py` — 6 instances → `OSError`, `subprocess.SubprocessError`
3. `file_cortex_core/search.py` — 2 instances → `OSError`, `PermissionError`
4. `file_cortex_core/duplicate.py` — 3 instances → `OSError`
5. `file_cortex_core/config.py` — 2 instances → `json.JSONDecodeError`, `OSError`
6. `file_cortex_core/context.py` — 2 instances → `OSError`
7. `file_cortex_core/format_utils.py` — 2 instances → `ValueError`

### CONST-1: Extract 20+ magic numbers into named constants

| File | Line(s) | Magic Number | Constant Name |
|------|---------|-------------|---------------|
| `format_utils.py` | 40-43 | 1024, 1048576, 1073741824 | `KB`, `MB`, `GB` |
| `format_utils.py` | 79 | 4, 1.5 | `ASCII_CHARS_PER_TOKEN`, `CJK_CHARS_PER_TOKEN` |
| `config.py` | 379 | 15 | `MAX_RECENT_PROJECTS` |
| `config.py` | 519 | 5 | `MAX_SESSION_HISTORY` |
| `file_io.py` | 131 | 8192 | `BINARY_CHECK_CHUNK_SIZE` |
| `file_io.py` | 140 | 0.3 | `BINARY_THRESHOLD` |
| `file_io.py` | 363 | 65536 | `ENCODING_DETECTION_BYTES` |
| `context.py` | 102,170 | 1048576 | `MAX_CONTEXT_READ_BYTES` |
| `duplicate.py` | 54 | 1048576 | `DEFAULT_HASH_CHUNK_SIZE` |
| `actions.py` | 91 | 1000 | `MAX_CONFLICT_ATTEMPTS` |
| `actions.py` | 433 | 300 | `DEFAULT_EXEC_TIMEOUT` |

### DUP-1: Extract process-termination utility (3 copy-paste locations)

Locations:
1. `file_cortex_core/actions.py:462-473`
2. `routers/ws_routes.py:209-218`
3. `routers/action_routes.py:221-227` and `265-276`

Create `file_cortex_core/process_utils.py` with `terminate_process(pid: int) -> None`.

### MISC-1: Other Python improvements
- `file_cortex_core/search.py:52` — `self.q` → `self.query`
- `file_cortex_core/search.py:127` — `self.pm` → `self.path_matcher`
- `file_cortex_core/config.py:183` — Add type annotation to `_lock`
- `file_cortex_core/config.py:133-134` — Use existing `MAX_LOG_SIZE`/`BACKUP_COUNT` constants
- `routers/services.py:55` — Remove `_ = project_root` dead assignment

---

## P1 — JavaScript Frontend

### API-2: Centralize api.js with `_post()` helper
- Create `_post(url, data)` → `return _fetch(url, { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data) })`
- Refactor 22 POST functions to use `_post()`
- Add 4 missing endpoints to `config.endpoints` in state.js

### SOCK-2: Add try/catch around `JSON.parse(event.data)` in WebSocket handlers
- `main.js:669` — search WebSocket
- `main.js:787` — tool execution WebSocket

### INIT-1: Decompose `App.init()` into sub-functions
- `_initGlobalKeyboard()` — keyboard shortcuts
- `_initSearchInput()` — search debounce and state persistence
- `_initContextMenu()` — click and contextmenu listeners
- `_initEditorShortcuts()` — Ctrl+S, Tab handling
- `_restoreSidebar()` — sidebar state restoration
- `_autoLoadLastProject()` — last project loading
- `_bindActionModal()` — action modal confirm button
- Each <20 lines

### GUARD-1: Add null guards to critical `getElementById` calls
- Create `const $ = (id) => document.getElementById(id)` helper
- Add null guards on 30+ DOM accesses

---

## P2 — CSS Improvements

### CSS-1: Reduce `!important` from 37 to <10
Strategy: Use higher-specificity selectors instead of `!important`
- `.app-shell .navbar { ... }` instead of `.navbar { ... !important }`
- `.app-shell .form-control { ... }` instead of `.form-control { ... !important }`

### CSS-2: Fix duplicate `.summary-bar` rules
- Lines 32 and 140 both define `.summary-bar` with conflicting properties
- Merge into single declaration

### CSS-3: Remove unused CSS rules
- `.staging-item` (never used in JS)
- `.search-result-item` (never used in JS)

### CSS-4: Use CSS variables for hardcoded colors
- 12 hardcoded color values should use `var(--*)` tokens

---

## P2 — HTML Accessibility

### A11Y-1: Add ARIA attributes
- Overlays: `role="dialog"`, `aria-modal="true"`
- Context menu: `role="menu"`, items `role="menuitem"`, `tabindex="0"`
- Sidebar: `role="navigation"`, `aria-label`
- Section toggles: `role="button"`, `tabindex="0"`, `aria-expanded`
- Toast container: `aria-live="polite"`
- Inputs: `aria-label` on all `<input>` and `<select>` elements

### A11Y-2: Semantic HTML
- Section header toggles: `<div>` → `<button>`
- Context menu items: `<div>` → `<button role="menuitem">`
- Bulk actions: `<div>` → `<div role="toolbar">`

### A11Y-3: Form validation
- Add `min`, `max`, `step` to numeric inputs
- Add `required` to project path input
