# FileCortex v5.8.2 - Comprehensive Architecture Analysis

**Date**: April 2026  
**Project**: FileCortex - Workspace Orchestrator for LLM Context Management  
**Version**: v5.8.2  
**Status**: Production-Ready (with caveats)

---

## 1. Executive Summary

FileCortex is a **micro-kernel architecture** that separates concerns across four tiers:
- **Core Library** (`file_cortex_core/`) - Platform-agnostic business logic
- **UI Layer** (`file_search.py` - Tkinter desktop, `web_app.py` - FastAPI web, `fctx.py` - CLI)
- **Infrastructure** (DataManager singleton, PathValidator security)
- **Test Suite** (194+ pytest tests)

**Strengths**: Clean separation, security-focused, thread-safe core, comprehensive testing  
**Weaknesses**: No packaging/distribution setup, limited documentation for extension, web API has no auth

---

## 2. Architecture Layer Breakdown

### 2.1 Core Library (`file_cortex_core/`)

#### A. **Config Layer** (`config.py` - 303 lines)
**Pattern**: Singleton with RLock (thread-safe)  
**Responsibility**: Project configuration, persistence, state management

```
DataManager (Singleton)
├── load() - Read config.json from ~/.filecortex/
├── save() - Atomic write with tempfile + os.replace (Windows-safe)
├── get_project_data() - Lazy-load project schema with defaults
├── batch_stage() - Add multiple paths atomically
├── MUTABLE_SETTINGS - Whitelist for security
├── Custom Tools/Categories APIs - RCE prevention via validation
└── Group/Favorites system - Project-level bookmarks
```

**Design Pattern**: Thread-Safety via RLock
- All public methods wrapped in `with self._lock:`
- Prevents race conditions in high-concurrency web scenarios
- Drawback: Recursive lock acquisition allowed (RLock, not Lock)

**Data Schema**:
- `last_directory`: Last opened project
- `projects`: Dict of `{norm_path: {schema}}`
- `recent_projects`: LRU list (max 15)
- `pinned_projects`: Workspace favorites
- Per-project extends: `excludes`, `staging_list`, `groups`, `notes`, `tags`, `custom_tools`, `prompt_templates`

**Critical Insights**:
1. Path normalization (`PathValidator.norm_path()`) is the SSOT (Single Source of Truth) for key consistency
2. Schema auto-completion ensures backward compatibility
3. Atomic persistence prevents config corruption on abnormal exit

---

#### B. **Security Layer** (`security.py` - 136 lines)
**Pattern**: Static utility class with validation helpers  
**Responsibility**: Path traversal prevention, sandbox enforcement

```
PathValidator
├── is_safe(target, root) - Strict boundary check (resolve() + is_relative_to)
├── norm_path(p) - Canonicalize paths (lowercase on Windows, POSIX separators)
├── validate_project(p) - Pre-flight checks before project registration
│   ├── Blocks UNC/network paths (Windows SMB leak prevention)
│   ├── Blocks system directories (/etc, Windows/, Program Files)
│   ├── Blocks single-letter drives and root paths
│   └── Rejects sensitive names (.git, .env, __pycache__)
```

**Security Model**:
- **Whitelist-based**: Only paths that satisfy `is_relative_to(root)` are safe
- **Prefix-based**: Blocks paths inside system folders (not just exact match)
- **Windows-aware**: Handles UNC, drive letters, path separators
- **Python <3.9 compatible**: Fallback for `is_relative_to` method

**Threat Matrix**:
| Threat | Mitigation | Evidence |
|--------|-----------|----------|
| Path traversal (`../../../etc/passwd`) | `resolve()` normalizes before check | `test_path_validator_is_safe_comprehensive` |
| Symlink escape | `resolve()` dereferences symlinks | Not explicitly tested; minor gap |
| UNC bypass (`\\?\C:\Windows`) | Explicit block for `//??` prefix | Tests in `test_security.py` |
| System dir access | Prefix-match block | `test_path_validator_blocked_prefixes` |

---

#### C. **File Operations Layer** (`actions.py` - 389 lines)
**Pattern**: Static utilities + Action Bridge  
**Responsibility**: File CRUD, batch operations, external tool execution

```
FileOps (Static methods)
├── batch_rename(pattern, replacement) - Regex rename with conflict detection & rollback
├── delete_file() - Handles read-only files via chmod
├── move_file() - Cross-directory movement
├── save_content() - Atomic write (tempfile + replace)
├── create_item() - File or directory creation
├── archive_selection() - ZIP creation with relative paths
├── batch_categorize() - Move files to classified folders

ActionBridge (External command execution)
├── _prepare_execution() - Cross-platform command prep
│   ├── Windows: Detects shell builtins (dir, echo) vs executables
│   ├── Unix: Always uses list-mode (shell=False)
│   └── Returns: (cmd_args, is_shell, context_dict)
├── execute_tool() - Synchronous execution with 300s timeout
├── create_process() - Popen wrapper for streaming
└── stream_tool() - Generator for real-time stdout capture
```

**Notable Design Choices**:
1. **Windows Command Detection**: Smart fallback from `shell=False` to `shell=True` if executable not found
2. **Rollback Strategy**: Named stack of renamed files for atomic recovery on failure
3. **Tempfile Pattern**: `mkstemp() + os.replace()` ensures atomic file saves on Windows

**Security Hardening**:
```python
# Context variables are format-safe:
context = {"path": str(p), "name": p.name, ...}
cmd_str = template.format(**context)

# But paths with {} are NOT pre-escaped! ⚠️
# Example: path="/proj/{evil}" → format expands {evil}
```

---

#### D. **Search Engine** (`search.py` - 295 lines)
**Pattern**: Generator + Thread pool executor  
**Responsibility**: Multi-mode file search with filtering

```
search_generator()
├── Mode 1: SMART - Path keyword matching (all tags, no negatives)
├── Mode 2: EXACT - Literal substring search
├── Mode 3: REGEX - Pattern matching (with ReDoS risk)
├── Mode 4: CONTENT - File content scanning
├── Features:
│   ├── Tag system: Positive/negative keywords
│   ├── .gitignore respect via pathspec library
│   ├── Binary detection (extension whitelist + heuristic)
│   ├── Max size limits (default 5MB per file)
│   └── Concurrency: ThreadPoolExecutor for content matching
└── Returns: Generator of {path, size, mtime, match_type, ...}

SearchWorker(Thread)
└── Worker thread for non-blocking UI search
```

**Architecture Insight**:
- Generator returns results as found (streaming, not batched)
- Shared thread pool via `atexit.register(SHARED_SEARCH_POOL.shutdown)`
- Adaptive batching: Processes up to 40 content-match futures before polling UI

**Known Limitations**:
1. Case sensitivity not applied consistently across modes
2. Regex mode targets full path but smart/exact target filename only
3. ReDoS vulnerability possible (local tool, acceptable risk)

---

#### E. **Utilities & Formatting** (`utils.py` - 432 lines)
**Pattern**: Static utility classes  
**Responsibility**: Text processing, path collection, token estimation

```
FileUtils (File operations)
├── is_binary() - Extension whitelist + byte heuristic (30% non-text threshold)
├── read_text_smart() - Encoding detection via charset-normalizer
│   ├── Reads first 65KB for encoding detection
│   ├── Falls back to UTF-8 on error
│   └── Supports max_bytes limit for preview (prevent OOM)
├── flatten_paths() - Recursive directory expansion + dedup
├── get_project_items() - Files matching excludes + gitignore
├── generate_ascii_tree() - Pretty-print directory structure
└── get_gitignore_spec() - Cached pathspec parser with mtime tracking

FormatUtils
├── format_size() - B/KB/MB/GB conversion
├── format_datetime() - YYYY-MM-DD HH:MM format
├── estimate_tokens() - **CJK-weighted token counter**
│   ├── ASCII: ~4 chars/token (code-heavy)
│   ├── CJK: ~1.5 chars/token (per character)
│   └── Formula: (ascii_count/4) + (non_ascii/1.5)
├── collect_paths() - Format paths with prefix/suffix/separator
└── ContextFormatter.to_markdown() - LLM context generator
    ├── Flattens directories recursively
    ├── Deduplicates with set()
    ├── Noise reduction via NoiseReducer.clean()
    └── Markdown code blocks with language tags

NoiseReducer
├── Strips minified code blocks (>500 chars single line)
├── Skips base64-like data (95%+ alphanumeric + /+=)
└── Preserves semantic content for LLM consumption
```

**CJK Token Estimation** (v5.8.2 enhancement):
- Modern models (GPT-4, Claude) use ~0.5-0.75 tokens/CJK char
- Formula uses 1.5 as approximation (reasonable for mixed workloads)
- Weighted average for multilingual projects

---

#### F. **Duplicate Finder** (`duplicate.py` - 150 lines)
**Pattern**: Worker thread  
**Responsibility**: Background duplicate detection

```
DuplicateWorker(Thread)
├── Phase 1: Group files by size (skip <2 files per size)
├── Phase 2: Hash each group (SHA256, 1MB chunking)
└── Returns: {size, hash, paths: []} for duplicates
```

**Performance Insight**:
- O(n) directory walk + O(files_per_size * m_avg_size) hashing
- Respects .gitignore to reduce workload
- Daemon thread kills on app exit

---

### 2.2 UI Tier

#### **Desktop** (`file_search.py` - 1388 lines)
**Pattern**: Tkinter MVC-lite  
**Key Components**:

```
FileCortexApp
├── Tab: Search
│   ├── Mode selector (Smart/Exact/Regex/Content)
│   ├── Tag bar (positive/negative keywords)
│   ├── Search results tree with sortable columns
│   └── Queue-based polling (SEARCH_POLL_MS=100ms)
├── Tab: Browse (Project tree, lazy-load)
├── Tab: Staging (Clearlist with filter)
├── Tab: Favorites (Groups of bookmarked paths)
├── Tab: Tools (Custom tool execution with log stream)
├── Preview pane (Read-only text with Ctrl+F search)
└── Context menus (17+ file operations)
```

**State Management**:
- `self.current_dir`: Active project
- `self.current_proj_config`: Live reference to DataManager project dict
- `self.staging_files`: In-memory list (synced to DataManager)
- `self.search_thread`: Active search worker

**Notable Pattern**: 
- Data isolation: UI reads/writes COPIES of config lists, not direct references
- Debounced stats calculation (300ms delay)
- Non-blocking search with queue polling

---

#### **Web API** (`web_app.py` - 783 lines)
**Pattern**: FastAPI REST + WebSocket  
**Endpoints** (40+ routes):

```
GET  /                 - HTML UI
GET  /api/content      - File text preview
POST /api/fs/children  - Directory listing
GET  /api/workspaces   - Recent + pinned projects
POST /api/open         - Register project

WebSockets:
WS   /ws/search        - Streaming search results
WS   /ws/actions/execute - Real-time tool output

File Ops:
POST /api/fs/rename, delete, move, save, create, archive

Project Memory:
POST /api/project/settings, tools, categories, favorites, notes, tags
```

**Security Features**:
- `get_valid_project_root()`: Whitelist check before operations
- `is_path_safe()`: Boundary validation
- `MUTABLE_SETTINGS` whitelist: Prevents config injection
- `max_length=10_000_000` on FileSaveRequest: Prevents OOM upload

**Deployment Issue** ⚠️:
- Static/template paths are relative (only works from `file_search/` dir)
- Should use absolute paths relative to `__file__`
- No CORS configuration (OK for localhost, risky if exposed)

---

#### **CLI** (`fctx.py` - ~80 lines)
Simple command-line wrapper for programmatic access:
```bash
fctx projects              # List registered
fctx stage <proj> <path>   # Add to staging
fctx categorize <proj>     # Move staged files
fctx run <proj> <tool>     # Execute tool on staging
```

**Limitation**: Directly modifies DataManager.data without going through batch_stage() (atomicity issue in multi-process scenario)

---

### 2.3 Cross-Cutting Concerns

#### **Configuration Loading Flow**
```
User opens project path
  ↓
PathValidator.validate_project()
  ↓ (checks: exists, is_dir, not_system, not_root)
DataManager.add_to_recent()
  ↓
DataManager.get_project_data()
  ↓ (lazy-load with schema defaults)
UI populates from config
  ↓
save_project_settings() → DataManager.save()
  ↓ (atomic: tempfile → os.replace)
~/.filecortex/config.json updated
```

#### **Thread Safety Model**
```
Multiple UIs (Desktop + Web) ⇄ Shared DataManager (Singleton + RLock)
  │
  └─→ config.json (atomic writes, can handle concurrent reads)
```

**Potential Race Condition**: Web UI calls `DataManager.load()` while Desktop calls `save()`
- Mitigated by atomic `os.replace()` (atomic on filesystems)
- Config schema is defensive (missing keys auto-filled)
- Worst case: load gets partial update, nothing corrupts

---

## 3. Software Engineering Quality Assessment

### 3.1 Strengths (/10)
| Aspect | Score | Notes |
|--------|-------|-------|
| **Separation of Concerns** | 9/10 | Clean micro-kernel; core is fully decoupled |
| **Security Hardening** | 8/10 | Path validation solid; API has auth gap |
| **Test Coverage** | 8/10 | 194 tests; good coverage of critical paths |
| **Documentation** | 6/10 | ROADMAP.md detailed; code comments sparse |
| **Error Handling** | 7/10 | Comprehensive try-except; some silent failures |
| **Performance** | 8/10 | Async search, lazy loading, memoization |
| **Maintainability** | 7/10 | Clear structure; some code duplication in UI |
| **Extensibility** | 7/10 | Core lib is reusable; UI tightly coupled |

### 3.2 Weaknesses
1. **No Packaging**: No setup.py, no PyPI distribution
2. **Web Auth**: Zero authentication on API endpoints
3. **Static Paths**: Web server requires running from specific directory
4. **API Rate Limiting**: None; DOS vulnerability if exposed
5. **Configuration Syntax**: No validation for custom tools (potential RCE if untrusted config imported)

---

## 4. Design Patterns Identified

| Pattern | Location | Usage |
|---------|----------|-------|
| **Singleton** | DataManager | Global state management |
| **Generator** | search_generator | Lazy evaluation of results |
| **Worker Thread** | SearchWorker, DuplicateWorker | Non-blocking operations |
| **Strategy** | Search modes (smart/exact/regex/content) | Pluggable algorithms |
| **Template Method** | ActionBridge._prepare_execution | Platform-specific variations |
| **Whitelist** | MUTABLE_SETTINGS, PathValidator | Security-by-default |
| **Atomic Write** | save_content, DataManager.save | Crash safety |

---

## 5. Code Complexity Analysis

**Cyclomatic Complexity Hotspots**:
- `on_tree_select_preview()`: ~12 branches (path resolution logic)
- `search_generator()`: ~18 branches (multi-mode logic)
- `_prepare_execution()`: ~15 branches (Windows shell detection)

**These are acceptable** for business logic; core is simple.

---

## 6. Recommendations for Engineering Health

### Tier 1 (Critical - Do Now)
1. **Add relative imports fix** for web static/templates
2. **Standardize exclude handling** (lowercase consistency)
3. **Fix search queue race condition** (process_queue polling)

### Tier 2 (Important - Next Sprint)
1. Create `setup.py` / `pyproject.toml`
2. Add basic auth to web API
3. Implement rate limiting

### Tier 3 (Nice-to-Have)
1. Extract UI state management to separate modules
2. Add configuration validation schema (pydantic)
3. Implement audit logging to file

---

## 7. Conclusion

FileCortex has a **production-quality architecture** with clear separation of concerns and security-first design. The micro-kernel approach makes the core reusable and testable. Main gaps are in **deployment/distribution** and **web API security**, not in core engineering quality.

**Overall Grade: B+/A- (85/100)**
- Architecture: A (9/10)
- Engineering: B+ (8/10)
- Production Readiness: B (7/10) - needs packaging/auth
