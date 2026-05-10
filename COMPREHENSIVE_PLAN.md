# FileCortex v6.3.1 Comprehensive Audit & Fix Plan

> **审计日期**: 2026-05-10
> **最终基线**: **`294 passed`** (`python -m pytest`), ruff clean
> **范围**: 全量架构审计 + 逐文件 Bug 排查 + 前端/后端一致性 + 73项新增单元测试 + 文档全部刷新

---

## Part A: 架构工程分析 (Software Architecture Audit)

### A1. SOLID 符合度

| 原则 | 评分 | 分析 |
|------|------|------|
| **S** 单一职责 | A- | `config.py` 同时管理日志初始化 + 配置管理，建议未来拆分；`search.py` 管理 worker + generator + pool |
| **O** 开闭原则 | B+ | `PathMatcher`/`ContentMatcher` 策略设计良好，但 `http_routes.py` 731行单一文件承载所有端点 |
| **L** 里氏替换 | A | Pydantic BaseModel 继承体系合理，无违反 |
| **I** 接口隔离 | A | 路由层 schemas/services/http_routes 三层分离清晰 |
| **D** 依赖倒置 | B | `DataManager()` 作为 Service Locator（而非 DI），`search_generator()` 直接调用 FileUtils 无接口抽象 |

### A2. DRY 重复模式（已识别）

- `file_search.py` 和 `http_routes.py` 内容获取逻辑重复 (`is_binary` + `read_text_smart` + 预览限制)
- `file_search.py` 和 `http_routes.py` 上下文生成逻辑重复 (format 选择 + to_xml/to_markdown 分支)
- `search.py` 目录遍历与 `file_io.py:get_project_items` 高度重复
- `file_search.py` 中 `clipboard_clear()/clipboard_append()` 重复出现 6 次

### A3. KISS 简洁性

- `actions.py:_prepare_execution` (363行) Shell vs 非Shell 分支逻辑复杂
- `search.py` content mode 使用 ThreadPoolExecutor + as_completed + batch，对小规模搜索过度设计
- `file_search.py` 1919行单体 GUI 类，违反单一职责

### A4. 模块耦合

| 耦合路径 | 问题 | 严重度 |
|----------|------|--------|
| `http_routes.py` → `common.py` → `ACTIVE_PROCESSES` | 模块级可变全局状态 | **中** |
| `search.py:28` → `SHARED_SEARCH_POOL` | 模块级 ThreadPoolExecutor，依赖 atexit | 低 |
| `__init__.py` → `gui/*` | 核心包导入 GUI 组件（可选依赖污染） | **高** |

---

## Part B: 逐文件 Bug 清单（v6.3.1 已修复）

### B1. 已修复 Bug

| ID | 文件:行号 | 类别 | 描述 | 状态 |
|----|-----------|------|------|------|
| BUG-001 | `search.py:280` | 运行时 | `as_completed(空dict)` 抛出 StopIteration | ✅ fixed |
| BUG-003 | `config.py:100` + `schemas.py:117` | 数据丢失 | `GlobalSettings` 缺少 `allowed_extensions`，前端设置被静默丢弃 | ✅ fixed |
| BUG-006 | `context.py:55,113` | 功能 | `to_markdown`/`to_xml` 无条件调用 NoiseReducer，忽略全局设置 | ✅ fixed |
| BUG-010 | `ws_routes.py:29` | 冗余 | `verify_ws_token` 内 `import os` 重复 | ✅ fixed |
| BUG-011 | `ws_routes.py:173` | 运行时 | `proc.stdout` 可能为 None 导致崩溃 | ✅ fixed |
| BUG-013 | `web_app.py:68` | 上下文 | `create_app()` 硬编码版本，改为使用 `__version__` | ✅ fixed |
| BUG-015 | `main.js:269-284` + `state.js:20` | 静默丢弃 | `allowed_extensions` 前后端不一致 (已修复)；`tokenThreshold: 100000` 与 `GlobalSettings: 128000` 不一致 | ✅ fixed |
| BUG-018 | `main.js:281,367,1054` | 运行时 | `bootstrap.Modal.getInstance()` 3处无空值检查 | ✅ fixed |
| BUG-023 | `mcp_server.py:214` | 类型 | `FileUtils.generate_ascii_tree` 参数应为 `pathlib.Path` | ✅ fixed |
| BUG-024 | `mcp_server.py:169-186` | 逻辑 | `register_workspace` 使用未归一化路径检查重复 | ✅ fixed |
| BUG-025 | `fctx.py` | 测试缺失 | CLI 模块无测试覆盖 | ✅ 新增 5 tests |

### B2. 代码债务（延迟到 v7.0）

| ID | 描述 | 优先级 |
|----|------|--------|
| DEBT-1 | `DataManager.data` 属性标记为 DEPRECATED 但全量使用 | P1 |
| DEBT-2 | `file_search.py` 1919行单体类需拆分为 Controller/View | P1 |
| DEBT-3 | CDN 资源无 SRI hash (`index.html:9-11,431-434`) | P3 |
| DEBT-4 | 前端端点字符串散落在 `api.js`，应集中于 `state.js:config.endpoints` | P2 |

---

## Part C: 前后端一致性校验 (v6.3.1)

### C1. 参数动态对齐表

| 参数 | 前端位置 | 后端位置 | 默认值 | 一致 |
|------|----------|----------|--------|------|
| `tokenThreshold` | `state.js:20` | `GlobalSettings.token_threshold:95` | **128000** | ✅ |
| `token_ratio` | `state.js:21` | `GlobalSettings.token_ratio:97` | **4.0** | ✅ |
| `preview_limit_mb` | `GlobalSettings.preview_limit_mb:94` | 后端模型 | **1.0** | ✅ |
| `allowed_extensions` | `main.js:263` | `GlobalSettings.allowed_extensions:100` | **""** | ✅ |
| `api_token` | `window.__FCTX_API_TOKEN__` | `web_app.py:22,430` | env var | ✅ |
| `apply_noise_reducer` | `schemas.py:30` | `context.py:55,118` | **True** | ✅ |
| `__version__` | `templates/index.html:8,25` | `file_cortex_core/__init__.py:3` | **6.3.1** | ✅ |
| `tokenThreshold-fallback` | `main.js:848` | `App.config.defaults.tokenThreshold` | **128000** | ✅ |

### C2. API Token 认证链路

```
1. 启动: FCTX_API_TOKEN 环境变量 → web_app.py:22 API_TOKEN
2. 模板注入: index.html:430 → window.__FCTX_API_TOKEN__
3. HTTP 请求: api.js:3-12 → X-API-Token header
4. WS 请求: main.js:632 → token query parameter
5. 中间件验证: web_app.py:43-63 (HTTP), ws_routes.py:27-33 (WS)
```

---

## Part D: 测试覆盖率 (294 tests)

### D1. 现有覆盖

| 模块 | v6.3.0 | v6.3.1 | 新增 | 覆盖率评估 |
|------|--------|--------|------|-----------|
| `config.py` | 15 | 24 | +9 | 90% (GlobalSettings 字段验证, 持久化边界) |
| `security.py` | 23 | 33 | +10 | 95% (UNC, POSIX, None/空值, 嵌套路径) |
| `search.py` | 25 | 31 | +6 | 90% (中断/取消, content模式大文件) |
| `file_io.py` | 12 | 12 | - | 75% |
| `format_utils.py` | 10 | 13 | +3 | 90% (分隔符转义, prefix/suffix) |
| `context.py` | 6 | 6 | - | 70% |
| `actions.py` | 18 | 29 | +11 | 90% (原子保存, 移动, 创建, 归档) |
| `duplicate.py` | 2 | 4 | +2 | 75% (取消扫描, 空目录) |
| `web_api` | 30+ | 43+ | +13 | 85% (Token/CORS/全局设置/异常处理) |
| `mcp_server` | 3 | 14 | +11 | 85% (搜索/注册/蓝图/统计/上下文) |
| `fctx.py` | **0** | **5** | +5 | 60% (open/projects/no-command/拒绝系统目录) |
| `frontend_contract` | 4 | 4 | - | 10% |
| **总计** | **221** | **294** | **+73** | |

### D2. 新增测试清单 (tests/test_comprehensive_v63.py)

**CLI (5 tests):**
- `test_cli_open_existing_path` / `test_cli_open_nonexistent_path` / `test_cli_open_system_dir_blocked`
- `test_cli_projects_list` / `test_cli_no_command_shows_help`

**MCP Server (11 tests):**
- 搜索(3): unauthorized / with results / respects limit
- 注册(2): new workspace / duplicate detection / nonexistent path
- 蓝图(1) / 列表(1) / 上下文XML+MD(2) / 统计(1)

**Web API 扩展 (13 tests):**
- 全局设置(3): allowed_extensions / settings alias / unknown field silent
- 项目(1): recent projects legacy / stage_all_with_excludes / stage_all_no_excludes
- 归档(1): cross-project blocked / generate_with_noise_reducer
- 认证(2): token header forward / CORS origin restricted / CORS wildcard
- 异常处理(2): global exception / production mode
- 其他(1): proj_config returns 403 for unregistered

**PathValidator 扩展 (10 tests):**
- 嵌套路径/同级目录阻止/UNC 阻止
- 尾部斜杠/None 输入/空字符串
- 系统目录/文件而非目录验证

**FileOps 扩展 (11 tests):**
- 原子保存/不存在文件/二进制拒绝/创建文件与目录/重复创建
- 移动/目标非目录/归档目录结构/批分类未定义

**Config 扩展 (9 tests):**
- 全局设置部分更新保留其他字段 / 无效类型
- 去重/固定切换/会话上限/模型验证/工具键验证/遍历阻止

**Search/Context/NoiseReducer/FormatUtils/Duplicate (14 tests):**
- 中断搜索/大文件跳过/逆搜索/CDATA转义/空路径
- noise reducer边界/分隔符转义/前缀后缀/数字格式化
- 取消扫描/空目录

---

## Part E: 版本变更记录 (v6.3.1)

### 代码修改

| 文件 | 变更 |
|------|------|
| `file_cortex_core/__init__.py` | 版本 6.3.0 → 6.3.1 |
| `file_cortex_core/config.py` | `GlobalSettings` 新增 `allowed_extensions` 字段 |
| `file_cortex_core/context.py` | `to_markdown`/`to_xml` 新增 `apply_noise_reducer` 参数 |
| `file_cortex_core/search.py` | `as_completed` StopIteration 明确捕获 |
| `routers/schemas.py` | `GenerateRequest` 新增 `apply_noise_reducer` 字段 |
| `routers/http_routes.py` | `generate_context` 传递 `apply_noise_reducer` 到 ContextFormatter |
| `routers/ws_routes.py` | `proc.stdout` None 防御；移除冗余 `import os` |
| `web_app.py` | FastAPI title 使用 `__version__` 变量 |
| `mcp_server.py` | `root` 类型修正为 `pathlib.Path`；归一化路径检查重复注册 |
| `static/js/state.js` | `tokenThreshold` 100000 → 128000 (对齐 GlobalSettings) |
| `static/js/main.js` | `bootstrap.Modal.getInstance()` 空值检查 x3 |
| `pyproject.toml` | 版本 6.3.0 → 6.3.1 |
| `tests/test_comprehensive_v63.py` | **新文件**: 73 项新增测试 |

---

## Part F: 未来路线图

### v6.3.x 短期维护
- [ ] `file_search.py` Controller/View 拆分
- [ ] CDN 资源 SRI hash
- [ ] 前端端点集中到 `config.endpoints`

### v7.0 中期规划
- [ ] DataManager 依赖注入重构（取代 Service Locator）
- [ ] `http_routes.py` 按功能域拆分
- [ ] 共享逻辑从 `file_search.py`/`http_routes.py` 提取到 core
- [ ] 前端 Playwright E2E 测试
- [ ] mypy strict mode 类型检查

### v8.0 长期愿景
- [ ] 插件系统 + 标准 Hook 接口
- [ ] 语义搜索 (Embedding-based)
- [ ] 本地 LLM 集成 (Ollama/llama.cpp)

---

## Part G: 验证清单

- [x] `ruff check .` — All checks passed (0 errors)
- [x] `python -m pytest` — **294 passed, 0 failed**
- [x] 版本号全场一致 — v6.3.1 (`__init__.py`, `pyproject.toml`, `web_app.py`, `file_search.py`, `templates/index.html`)
- [x] `tokenThreshold` 前后端一致 — 128000
- [x] `allowed_extensions` 前后端一致 — GlobalSettings + frontend 发送 + settings 模态框
- [x] `apply_noise_reducer` 参数链路 — schema → route → ContextFormatter → NoiseReducer
- [x] API Token 认证链路 — env → template → HTTP header + WS query → middleware
- [x] `bootstrap.Modal.getInstance()` null 保护 — 全 4 处调用点
- [x] MCP server `root` 类型安全 — `pathlib.Path()` 包装
- [x] 文档全部刷新 — README, DEVELOPER_GUIDE, ROADMAP, ANALYSIS_REPORT, FRONTEND_ANALYSIS, tests/README
