# FileCortex v7.0 综合审计、Code Review 与工程化计划

> **审计日期**: 2026-05-23 | **版本基线**: v6.3.3 (372 passed) | **审计范围**: 全量源码 (22 源文件, ~6200 行)

---

## Part 1: 架构工程分析

### 1.1 架构评估 (SOLID 评分)

| 原则 | 评分 | 分析 |
|------|------|------|
| **S** - 单一职责 | 7/10 | `DataManager` 承担了过多的职责（配置管理、持久化、业务逻辑），混合了 Repository 和 Service 层。`FileCortexApp` (1835行) 仍然是一个 God Class。 |
| **O** - 开闭原则 | 6/10 | 搜索策略已实现策略模式 (`PathMatcher`/`ContentMatcher`)，但文件操作 (`FileOps`) 缺乏可扩展接口。新的文件类型处理器需要修改现有代码。 |
| **L** - 里氏替换 | 8/10 | Pydantic 模型继承合理，`DataManager.create()`/`activate()` DI 机制设计良好。 |
| **I** - 接口隔离 | 7/10 | `FileUtils` 工具类过大 (523行)，混合了 I/O、缓存、元数据、树生成等不同关注点。 |
| **D** - 依赖倒置 | 7/10 | Web 层通过 FastAPI `Depends` 注入 `DataManager`，但核心模块直接实例化 `DataManager()` (`actions.py:329`)。 |

**总体架构评分: 7.0/10** — 对于一个工具型桌面/Web应用来说属于良好水平。

### 1.2 分层模型分析

```
┌─ Entry Points ─────────────────────────────┐
│ file_search.py (Desktop/Tkinter)  1835 LOC │  ← God Class, 需要拆分
│ web_app.py (Web/FastAPI)            135 LOC │  ✓ 精简入口
│ fctx.py (CLI/argparse)              135 LOC │  ✓ 职责单一
│ mcp_server.py (MCP/FastMCP)         315 LOC │  ✓ 职责单一
├─ Route Layer ──────────────────────────────┤
│ http_routes.py    27 LOC  (聚合)           │  ✓ 合理
│ project_routes.py 184 LOC                  │  ✓ 职责清晰
│ fs_routes.py      327 LOC                  │  ✓ 职责清晰
│ action_routes.py  278 LOC                  │  ⚠ execute_tool 过长
│ ws_routes.py      227 LOC                  │  ⚠ 重复的进程管理逻辑
│ schemas.py        212 LOC                  │  ✓ Pydantic 模型
│ services.py       109 LOC                  │  ✓ 服务层
│ common.py          10 LOC                  │  ✓ 共享状态
├─ Core Kernel ──────────────────────────────┤
│ config.py         596 LOC                  │  ⚠ DataManager 过重
│ security.py       204 LOC                  │  ✓ 安全模块
│ search.py         376 LOC                  │  ✓ 策略化搜索
│ file_io.py        523 LOC                  │  ⚠ FileUtils 过大
│ context.py        203 LOC                  │  ✓ 上下文生成
│ actions.py        573 LOC                  │  ⚠ 混合工具执行与文件操作
│ format_utils.py   130 LOC                  │  ✓ 工具函数
│ duplicate.py      131 LOC                  │  ✓ 查重模块
└─ GUI Components ───────────────────────────┘
│ batch_rename.py   205 LOC                  │  ✓ 独立组件
│ duplicate_finder.py 260 LOC                │  ✓ 独立组件
│ path_collection.py 156 LOC                 │  ✓ 独立组件
```

### 1.3 架构优势

1. **微内核设计**: 核心包 `file_cortex_core` 独立于任何 UI/传输层，支持 4 种入口复用
2. **Pydantic V2 驱动**: 强类型配置，自动校验，自愈能力
3. **安全沙盒**: `PathValidator` 统一路径验证，UNC 拦截，敏感目录保护
4. **原子持久化**: `tempfile + os.replace` + Windows 重试机制
5. **策略化搜索**: 4 种搜索模式通过策略模式解耦
6. **共享遍历**: `walk_filtered()` 统一目录遍历
7. **DI 支持**: `DataManager.create/reset/activate` 三级实例管理

### 1.4 架构不足

1. **God Class**: `FileCortexApp` (1835行) 违反 SRP，混合了 UI 构建、事件处理、业务逻辑、状态管理
2. **过程管理重复**: 进程超时/终止逻辑在 `action_routes.py`、`ws_routes.py`、`actions.py` 三处重复
3. **核心层直接依赖单例**: `FileOps.batch_categorize` 直接 `DataManager()` 获取配置
4. **缺少抽象接口**: 文件操作、搜索策略等核心能力缺少 Protocol/ABC 定义
5. **测试耦合**: conftest.py 直接 import `web_app.app`，导致所有测试加载 FastAPI 应用

---

## Part 2: 项目定位与竞品分析

### 2.1 项目定位

FileCortex 定位为 **"AI 友好的工作区编排工具"** — 介于文件管理器与 AI 上下文生成器之间的利基市场：

| 维度 | FileCortex | 传统文件管理器 | AI 上下文工具 |
|------|-----------|---------------|--------------|
| 文件搜索 | ✓ 多模式策略 | ✓ 基础 | ✗ |
| AI 上下文导出 | ✓ XML/MD | ✗ | ✓ |
| Token 估算 | ✓ | ✗ | ✓ (部分) |
| 项目编排 | ✓ 暂存/分类 | ✗ | ✗ |
| 多端访问 | ✓ 4端 | ✓ (1-2端) | ✗ (通常仅Web) |
| MCP 协议 | ✓ | ✗ | ✗ |

### 2.2 竞品对比

| 项目 | 类型 | 优势 | FileCortex 差异点 |
|------|------|------|-------------------|
| **repomix** | CLI 上下文生成 | 轻量、专注 | FC 有 GUI/Web/MCP，更全面 |
| **gptme** | AI Agent 工具 | 集成 LLM | FC 专注于文件编排而非 LLM 交互 |
| **aider** | AI 编程助手 | 深度代码理解 | FC 是编排层，不处理代码逻辑 |
| **Cursor Context** | IDE 集成 | 无缝体验 | FC 独立工具，无 IDE 耦合 |
| **treesheet/cliptext** | 文件上下文 | 轻量 | FC 有分类/查重/工具执行 |
| **ollama-code-context** | 本地 AI | 本地推理 | FC v8.0 路线图已规划 |

### 2.3 参考学习点

1. **repomix**: 简洁的 CLI 设计风格，Token 预算可视化
2. **aider**: `.aiderignore` 模式 — FC 的 gitignore 集成思路与之相似但更灵活
3. **ripgrep**: 多线程搜索架构 — FC 可参考其并行策略
4. **VS Code Search**: 实时搜索 + 预览双面板 — FC Desktop 已实现

### 2.4 未来路线图建议

**短期 (v7.0)**:
- 代码质量加固：修复已发现的 BUG，补全测试覆盖
- 进程管理去重：统一为 `ProcessManager` 服务

**中期 (v7.1-7.5)**:
- 插件系统：标准 Hook 接口 (`on_search`, `on_export`, `on_file_open`)
- 虚拟滚动：Web 端支持万级文件树
- 拖拽支持：文件拖入暂存面板
- E2E 测试：Playwright 前端测试

**长期 (v8.0+)**:
- 本地 LLM 集成 (Ollama/llama.cpp)
- 语义搜索 (Embedding 向量)
- 增量索引 (文件指纹缓存)

---

## Part 3: 完整 Code Review — BUG 清单

### 3.1 BUG 列表 (按严重程度排序)

#### CRITICAL (可能导致数据丢失或安全风险)

| # | 文件 | 行号 | 问题 | 修复方案 |
|---|------|------|------|----------|
| C-1 | `file_search.py` | 1534 | `FileOps.save_content(str(self.current_preview_path), content[:-1])` — `content[:-1]` 用切片删除末尾换行符，但 ScrolledText 的 `get("1.0", tk.END)` 返回内容中tk自动追加的 `\n` 并非文件原始内容。如果文件原本不以 `\n` 结尾，这会丢失最后一个字符 | 改用 `content.rstrip("\n")` 或 `content.removesuffix("\n")` 更安全；或者用 `self.preview_text.get("1.0", "end-1c")` |
| C-2 | `actions.py` | 436 | `DataManager().data.get("execution_timeout", 300)` — 使用已废弃的 `.data` dict API，且 `AppConfig` 中根本无 `execution_timeout` 字段，永远返回默认值 300 | 改用 `os.getenv("FCTX_EXEC_TIMEOUT", "300")` (整数转换) 或在 `GlobalSettings` 中添加该字段 |
| C-3 | `file_search.py` | 1100-1104 | `rel = p.relative_to(self.current_dir) if self.current_dir in p.parents else p.name` — 当文件直接位于项目根目录时，`self.current_dir in p.parents` 为 False，导致相对路径退化为仅文件名 | 条件应为 `self.current_dir == p.parent or self.current_dir in p.parents` |

#### HIGH (功能异常或逻辑错误)

| # | 文件 | 行号 | 问题 | 修复方案 |
|---|------|------|------|----------|
| H-1 | `file_io.py` | 297-339 | `flatten_paths` 内部有自己的 `os.walk` 实现，没有复用 `walk_filtered`，导致两套遍历逻辑需要同步维护 | 重构为调用 `walk_filtered` |
| H-2 | `search.py` | 286-287 | `if count >= query.max_results: pass` — 死代码，空 if 块无意义 | 删除此死代码 |
| H-3 | `file_search.py` | 404-412 | tree_search 的 columns 定义被立即覆盖 — 先设置 columns 为 `("file", "path", "size", "mtime", "ext")`，然后又设为 `("abs_path", "file", "path", "size", "mtime", "ext")`，导致列顺序混乱 | 直接使用最终定义，移除中间覆盖 |
| H-4 | `routers/ws_routes.py` | 103 | `asyncio.create_task(asyncio.to_thread(run_search))` — 创建了 task 但从未被 await 或取消处理，如果搜索线程抛异常，task 会静默丢失 | 添加 task 异常处理或在 finally 中 cancel |
| H-5 | `config.py` | 437-439 | `get_project_data()` 返回 `model_dump()` dict，修改这个 dict 不会反映到实际模型上。调用方（如 Desktop GUI）通过 `self.current_proj_config["staging_list"]` 修改的是临时 dict，需要 `save()` 才能持久化 — 但 `get_project_data()` 每次都返回新的 dump | 明确文档说明，或改为返回 Model 对象引用。Desktop 端应改用 `get_project_data_obj()` |
| H-6 | `mcp_server.py` | 236 | `from file_cortex_core import FormatUtils, NoiseReducer` — 函数体内部重复导入，`NoiseReducer` 已在顶层 `__init__.py` 导出 | 移到函数外或使用顶层导入 |
| H-7 | `file_search.py` | 1815 | `_update_pin_button` 使用 `self.data_mgr.data.get("pinned_projects", [])` — 废弃的 dict API | 改用 `self.data_mgr.config.pinned_projects` |

#### MEDIUM (代码质量、性能、可维护性)

| # | 文件 | 行号 | 问题 | 修复方案 |
|---|------|------|------|----------|
| M-1 | `file_search.py` | 全文 | `FileCortexApp` 1835行 God Class — 混合了 UI、业务、状态 | 阶段性拆分 (见执行计划) |
| M-2 | `actions.py` | 328-351 | `batch_categorize` 直接 `DataManager()` 获取单例，破坏 DI | 注入 dm 参数 |
| M-3 | `routers/action_routes.py` + `ws_routes.py` | 多处 | 进程超时/终止逻辑重复 3 次 | 提取为 `ProcessManager` |
| M-4 | `search.py` | 28 | `SHARED_SEARCH_POOL` 全局线程池 — `atexit.register(shutdown, wait=False)` 可能导致任务丢失 | 改为懒初始化或使用 `wait=True` |
| M-5 | `file_search.py` | 1609 | `ctx_copy_file_to_os` 使用 f-string 构造 AppleScript，存在注入风险 | 使用 `subprocess` 安全参数传递 |
| M-6 | `file_io.py` | 297 | `flatten_paths` 第二个 `os.walk` 不支持 `stop_event` 取消 | 添加 stop_event 参数 |
| M-7 | `format_utils.py` | 57 | `format_datetime` 未指定 timezone，使用本地时区 | 对于跨设备场景应使用 UTC 或明确标注 |

#### LOW (代码风格、文档)

| # | 文件 | 行号 | 问题 |
|---|------|------|------|
| L-1 | `file_search.py` | 39 | `TOKEN_RATIO = 4` 模块级常量未使用 (search.py 内部有自己的估算) |
| L-2 | `file_search.py` | 83 | `self.results_count = 0` 在 `process_queue` 中未实际使用 |
| L-3 | `routers/common.py` | 9 | `ACTIVE_PROCESSES` 无大小限制，理论上可无限增长 |
| L-4 | `config.py` | 213 | `_init_data` 在 `__new__` 中调用，若子类化可能导致问题 |
| L-5 | `duplicate_finder.py` | 160 | `self.current_dir in p.parents` 与 C-3 同样的根目录直接子文件问题 |

### 3.2 安全审计

| # | 位置 | 问题 | 风险等级 |
|---|------|------|----------|
| S-1 | `actions.py:388-410` | Windows shell 模式下，虽然对 `"` 和 `%` 做了转义，但 `&`, `|`, `<`, `>` 等仍可能通过非预期路径触发 shell | Medium |
| S-2 | `ws_routes.py:27` | WebSocket token 通过 query param 传递，可能被日志记录 | Low |
| S-3 | `file_search.py:1608-1611` | AppleScript 字符串拼接注入 | Medium |
| S-4 | `routers/common.py` | `ACTIVE_PROCESSES` 字典可被任意路由添加条目，无访问控制 | Low |

---

## Part 4: 执行计划 — BUG 修复与测试

### 4.1 修复计划 (按执行顺序)

#### 阶段 A: Critical BUG 修复 (3项)

**A-1: 修复 save_content 截断问题**
- 文件: `file_search.py:1533-1534`
- 当前: `content = self.preview_text.get("1.0", tk.END)` → `FileOps.save_content(str(self.current_preview_path), content[:-1])`
- 修改为: `content = self.preview_text.get("1.0", "end-1c")` → `FileOps.save_content(str(self.current_preview_path), content)`
- 测试: 新增 `test_preview_save_no_truncation`

**A-2: 修复废弃 API 使用**
- 文件: `actions.py:436`
- 当前: `DataManager().data.get("execution_timeout", 300)`
- 修改为: `int(os.getenv("FCTX_EXEC_TIMEOUT", "300"))`
- 同步修改: `file_search.py:1815` 的 `_update_pin_button` 改用 `self.data_mgr.config.pinned_projects`

**A-3: 修复 relative_to 根目录文件退化**
- 文件: `file_search.py:1100-1104`
- 当前: `p.relative_to(self.current_dir) if self.current_dir in p.parents else p.name`
- 修改为: 使用 try/except 包裹 `p.relative_to(self.current_dir)`
- 同步修复: `duplicate_finder.py:158-161`

#### 阶段 B: High BUG 修复 (7项)

**B-1: 移除 search.py 死代码**
- 文件: `search.py:286-287`
- 删除 `if count >= query.max_results: pass`

**B-2: 修复 tree_search columns 覆盖问题**
- 文件: `file_search.py:360-413`
- 统一为最终 columns 定义，删除中间覆盖

**B-3: 添加 WebSocket task 异常处理**
- 文件: `ws_routes.py:103-120`
- 添加 try/except 处理 search_task 异常

**B-4: Desktop 端改用 get_project_data_obj**
- 文件: `file_search.py:710`
- 将 `get_project_data()` 改为 `get_project_data_obj()` 并适配后续代码
- 注: 此变更影响面广，需要仔细适配所有 `self.current_proj_config` 的使用

**B-5: 移除 mcp_server.py 函数内重复导入**
- 文件: `mcp_server.py:204, 236`
- 移到文件顶部或使用已有顶层导入

**B-6: 修复 _update_pin_button 废弃 API**
- 文件: `file_search.py:1813-1816`
- 改用 `self.data_mgr.config.pinned_projects`

**B-7: flatten_paths 添加 stop_event 支持**
- 文件: `file_io.py:261-341`
- 添加 `stop_event` 参数并在 os.walk 循环中检查

#### 阶段 C: Medium 改进 (3项，可选)

**C-1: AppleScript 注入防护**
- 文件: `file_search.py:1608-1611`
- 对文件路径中的引号进行转义

**C-2: SHARED_SEARCH_POOL atexit 修复**
- 文件: `search.py:29`
- 改为 `wait=True` 或懒初始化

**C-3: ACTIVE_PROCESSES 大小限制**
- 文件: `routers/common.py`
- 添加最大进程数限制 (如 50)

### 4.2 测试计划 (新增测试)

#### 新测试文件: `tests/test_bugfix_v7.py`

覆盖以下场景 (预计 35-40 项测试):

| # | 测试函数 | 覆盖 BUG | 验证内容 |
|---|----------|----------|----------|
| 1 | `test_save_content_no_truncation` | A-1 | 保存的文件末尾字符不被截断 |
| 2 | `test_save_content_preserves_newline` | A-1 | 文件末尾有换行时正确保留 |
| 3 | `test_save_content_no_newline` | A-1 | 文件末尾无换行时不追加 |
| 4 | `test_execution_timeout_env_var` | A-2 | FCTX_EXEC_TIMEOUT 环境变量生效 |
| 5 | `test_execution_timeout_default` | A-2 | 默认超时为 300 |
| 6 | `test_relative_path_root_files` | A-3 | 项目根目录下的文件获得正确相对路径 |
| 7 | `test_relative_path_nested_files` | A-3 | 嵌套目录中的文件获得正确相对路径 |
| 8 | `test_relative_path_deeply_nested` | A-3 | 深层嵌套文件的相对路径 |
| 9 | `test_search_no_dead_code` | B-1 | search_generator 正确达到 max_results 上限 |
| 10 | `test_mcp_file_stats_imports` | B-5 | MCP server 无内部重复导入 |
| 11 | `test_pin_button_uses_config_api` | B-6 | pin 状态从 config.pinned_projects 读取 |
| 12 | `test_flatten_paths_empty` | B-7 | flatten_paths 空输入返回空列表 |
| 13 | `test_flatten_paths_stop_event` | B-7 | stop_event 能中断 flatten_paths |
| 14 | `test_format_datetime_returns_string` | M-7 | format_datetime 总返回字符串 |
| 15 | `test_noise_reducer_none_input` | - | NoiseReducer.clean(None) 返回空字符串 |
| 16 | `test_path_validator_empty_root` | - | is_safe 空根路径返回 False |
| 17 | `test_path_validator_relative_target` | - | is_safe 相对路径正确解析 |
| 18 | `test_data_manager_create_independent` | - | DataManager.create() 独立于单例 |
| 19 | `test_data_manager_activate_context` | - | activate() 上下文管理器正确恢复 |
| 20 | `test_batch_rename_conflict_resolution` | - | 冲突文件名自动添加后缀 |
| 21 | `test_batch_rename_rollback` | - | 重命名失败时回滚已执行的操作 |
| 22 | `test_archive_creates_zip` | - | 归档操作生成有效的 ZIP 文件 |
| 23 | `test_create_item_file` | - | 创建文件成功 |
| 24 | `test_create_item_dir` | - | 创建目录成功 |
| 25 | `test_create_item_duplicate` | - | 创建已存在项目报错 |
| 26 | `test_delete_nonexistent` | - | 删除不存在的文件报错 |
| 27 | `test_move_file_cross_project_blocked` | - | 跨项目移动被阻止 |
| 28 | `test_move_file_to_nonexistent_dir` | - | 移动到不存在的目录报错 |
| 29 | `test_context_xml_cdata_escaping` | - | XML 中 ]]> 正确转义 |
| 30 | `test_context_markdown_empty_paths` | - | 空路径列表生成空内容 |
| 31 | `test_search_content_mode_basic` | - | content 模式搜索基本功能 |
| 32 | `test_search_regex_invalid_pattern` | - | 无效正则不会崩溃 |
| 33 | `test_search_inverse_mode` | - | 反向匹配模式正确 |
| 34 | `test_gitignore_respected` | - | gitignore 规则被遵守 |
| 35 | `test_gitignore_no_gitignore_file` | - | 无 .gitignore 时正常工作 |
| 36 | `test_token_estimate_mixed` | - | 混合 ASCII/CJK 文本的 token 估算 |
| 37 | `test_collect_paths_relative` | - | 相对路径模式正确 |
| 38 | `test_collect_paths_absolute` | - | 绝对路径模式正确 |
| 39 | `test_collect_paths_dir_suffix` | - | 目录后缀正确追加 |
| 40 | `test_resolve_project_root_nested` | - | 嵌套项目正确匹配最长路径 |

### 4.3 执行顺序总览

```
Step 1: 修复 A-1 (save_content 截断)        → file_search.py
Step 2: 修复 A-2 (废弃 API)                  → actions.py, file_search.py
Step 3: 修复 A-3 (relative_to 退化)           → file_search.py, duplicate_finder.py
Step 4: 修复 B-1 (死代码删除)                 → search.py
Step 5: 修复 B-2 (columns 覆盖)              → file_search.py
Step 6: 修复 B-5 (重复导入)                   → mcp_server.py
Step 7: 修复 B-6 (pin_button 废弃 API)        → file_search.py
Step 8: 修复 B-7 (flatten_paths stop_event)   → file_io.py
Step 9: 修复 C-1 (AppleScript 注入)           → file_search.py
Step 10: 编写 test_bugfix_v7.py (40 项测试)
Step 11: 运行全量测试验证
Step 12: 更新版本号与文档
```

---

## Part 5: 架构改进路线图

### Phase 1 (v7.0): 稳定性加固
- 修复所有 Critical/High BUG
- 补全测试覆盖至 400+
- 进程管理统一为 `ProcessManager`

### Phase 2 (v7.1): 架构瘦身
- 拆分 `FileCortexApp` 为 5-6 个 mixin/panel 类
- `FileUtils` 拆分为 `FileReader`, `FileWalker`, `FileMetadata`
- `DataManager` 拆分 Repository 与 Service 职责

### Phase 3 (v7.5): 插件生态
- 定义 `FileCortexPlugin` Protocol
- 实现 Hook 系统: `on_search`, `on_export`, `on_file_open`, `on_project_load`
- 插件注册与发现机制

### Phase 4 (v8.0): 智能化
- 本地 Embedding 模型集成
- 语义搜索
- 增量索引

---

## 附录: 技术债务清单

| 类别 | 项 | 优先级 | 工作量估计 |
|------|-----|--------|-----------|
| 架构 | God Class 拆分 | P2 | 3-5天 |
| 架构 | 进程管理去重 | P1 | 1天 |
| 安全 | AppleScript 注入 | P1 | 0.5天 |
| 性能 | flatten_paths 复用 walk_filtered | P2 | 1天 |
| 性能 | 全局线程池优化 | P3 | 0.5天 |
| 测试 | WebSocket 流测试 | P2 | 1天 |
| 测试 | 前端 E2E 测试 | P3 | 2-3天 |
| 文档 | API 文档自动生成 | P3 | 1天 |
| 类型 | mypy 100% 覆盖 | P3 | 2-3天 |
