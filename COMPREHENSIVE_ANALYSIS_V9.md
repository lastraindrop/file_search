# FileCortex v6.5.0 — 全面架构审计、Code Review 与执行计划 (V9)

> **审计版本**: 6.5.0 | **审计日期**: 2026-06-15 | **测试基线**: 629 passed (195s) | **Ruff**: 0 errors
> **审计方法**: 5 个并行 subagent 深度审查（核心层 / Web·API 层 / 前端 / 测试覆盖 / 竞品研究）+ 主审计手工复核
> **代码规模**: ~19,215 行（Python / JS / HTML / CSS / MD）| **核心源**: ~6,400 行 Python + ~1,700 行 JS

---

## 目录

- [Part 1: 架构工程与设计分析](#part-1-架构工程与设计分析)
- [Part 2: 方向定位与竞品分析](#part-2-方向定位与竞品分析)
- [Part 3: 完整 Code Review 与 BUG 清单](#part-3-完整-code-review-与-bug-清单)
- [Part 4: 落地评估与执行计划](#part-4-落地评估与执行计划)
- [附录 A: 修改位置索引](#附录-a-修改位置索引)
- [附录 B: 测试补强计划](#附录-b-测试补强计划)

---

## Part 1: 架构工程与设计分析

### 1.1 总体架构评估

**架构模式**: 微内核 (Microkernel) + 分层架构 (Layered) + 多接入端 (Multi-Access)

```
┌─────────────────────────────────────────────────────────────────┐
│  接入层 (Access Layer) — 4 端                                    │
│  ┌──────────┐ ┌──────────────┐ ┌──────┐ ┌──────────────────┐    │
│  │ Desktop  │ │ Web FastAPI  │ │ CLI  │ │ MCP Server       │    │
│  │ Tkinter  │ │ REST + WS    │ │fctx  │ │ FastMCP (mock    │    │
│  │file_search│ │web_app+router│ │.py   │ │ fallback)        │    │
│  └────┬─────┘ └──────┬───────┘ └──┬───┘ └────────┬─────────┘    │
├───────┴──────────────┴────────────┴──────────────┴──────────────┤
│  路由层 (Route Layer) — routers/                                │
│  project_routes · fs_routes · action_routes · ws_routes         │
│  schemas (Pydantic) · services (业务) · common (ProcessManager) │
│  http_routes (合并层)                                            │
├─────────────────────────────────────────────────────────────────┤
│  核心层 (Core Microkernel) — file_cortex_core/                  │
│  config (DataManager SSOT) · security (PathValidator)           │
│  search (SearchWorker + 4 模式) · context (OOM 保护导出)        │
│  file_io (walk_filtered) · actions (FileOps + ActionBridge)     │
│  duplicate (SHA256) · format_utils · process_utils              │
│  gui/ (BatchRename · DuplicateFinder · PathCollection)          │
├─────────────────────────────────────────────────────────────────┤
│  持久层 (Persistence)                                            │
│  JSON config (~/.filecortex/) · lru_cache (编码/gitignore)      │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 SOLID 评分（v6.5.0 更新）

| 原则 | 评分 | 说明 |
|------|------|------|
| **S** 单一职责 | 8/10 | 核心模块职责清晰；`file_search.py` (1832 行) 偏重，受限于 Tkinter 单体模式 |
| **O** 开闭原则 | 7/10 | 搜索策略 (`PathMatcher`/`ContentMatcher`) 可扩展；但接入层需手动注册 |
| **L** 里氏替换 | 8/10 | `DataManager.create()` / `activate()` 支持测试替换（v6.3.2 DI） |
| **I** 接口隔离 | 7/10 | Router 按域拆分良好；`DataManager` 接口较宽（28 方法） |
| **D** 依赖倒置 | 7/10 | FastAPI `Depends` 注入；但核心层 `SHARED_SEARCH_POOL` 全局单例 + `DataManager()` 直接实例化 |

### 1.3 架构优点（继承自 v6.4 并在 v6.5 巩固）

1. **Pydantic V2 模型驱动配置**: `AppConfig → ProjectConfig → SearchSettings` 强类型链路 + 自愈
2. **多接入端解耦**: 四端共享核心层；GUI 组件 `try/except ImportError` 支持 headless
3. **策略化搜索**: 匹配逻辑与遍历逻辑分离（`PathMatcher`/`ContentMatcher`）
4. **安全沙盒**: `PathValidator` UNC 拦截、敏感目录保护、`Path.resolve()` 符号链接防护（v6.5.0 SEC-1）
5. **原子持久化**: `tempfile + os.replace` + Windows 重试保证配置文件写入不损坏
6. **线程安全**: `DataManager._lock (RLock)` + `activate()` 上下文管理器（v6.5.0 SEC-3）
7. **OOM 保护**: 上下文导出限流 `MAX_EXPORT_FILES=500` / `MAX_TOTAL_CONTENT_BYTES=50MB`（v6.5.0 OOM-1）
8. **进程容器**: `ProcessManager` 线程安全、容量限制 50、旧 API 别名（v6.5.0 PM-1/2）
9. **参数动态对齐**: 前后端关键参数经 `GlobalSettings` 单一来源校验（v6.5.0 HARD-1/2）
10. **Google Style 全规范审计**: 23 处日志规范化、22 处冗余绑定清理、8 处类型注解补全

### 1.4 架构问题与改进方向（v6.5.0 新发现）

| 编号 | 问题 | 严重度 | 位置 | 建议 |
|------|------|--------|------|------|
| **ARCH-1** | `file_search.py` 单体 1832 行 | Medium | `file_search.py` | 拆分为 `SearchPanel` / `StagingPanel` / `PreviewPanel` 子组件 |
| **ARCH-2** | `SHARED_SEARCH_POOL` 全局线程池单例 | Low | `search.py:28` | 改为按需创建 + 显式生命周期管理；interpreter 关闭后 submit 会 `RuntimeError` |
| **ARCH-3** | `DataManager._lock` 是类级 RLock，所有 `create()` 实例共享 | Low | `config.py:187` | 独立实例应使用独立锁，避免与单例争用 |
| **ARCH-4** | 错误处理不统一：核心层 `return None/""`，路由层 `HTTPException` | Low | 多处 | 引入异常层级 `AppError → NotFoundError / SecurityError` |
| **ARCH-5** | 无 CSP（Content-Security-Policy）| Medium | `templates/index.html` | 50+ 内联 `onclick` 阻碍 CSP 落地；需迁移到 `addEventListener` |
| **ARCH-6** | MCP Server 为 mock 回退，非真实可运行 | High | `mcp_server.py:21-55` | `mcp` 包未列入依赖；README 宣称的 "AI Agent 原生调用" 无法开箱即用 |
| **ARCH-7** | `pyproject.toml` 打包缺漏 `routers` 包 | **Critical** | `pyproject.toml:50` | `pip install .` 后 `web_app` 因 `from routers...` 失败 |
| **ARCH-8** | 同步阻塞端点占用线程池 | Medium | `action_routes.py:187` | `proc.communicate(timeout=300)` 在 sync endpoint 中可耗尽线程池 |
| **ARCH-9** | 无数据库层，纯 JSON 持久化 | Info | `config.py` | 当前规模合理；大规模需 SQLite |
| **ARCH-10** | 前端无构建系统，原生 ES6 模块 | Info | `static/js/` | 可引入 Vite/esbuild 打包优化 |

---

## Part 2: 方向定位与竞品分析

### 2.1 项目定位

**FileCortex** 定位为 **本地优先、AI 友好的工作区编排工具** (Local-First AI-Friendly Workspace Orchestrator)。

核心价值主张:
- **LLM 上下文生成**: 将项目文件转换为 Markdown/XML 格式 + Token 估算 + OOM 保护
- **多维度文件搜索**: smart/exact/regex/content 四模式搜索引擎
- **工作区编排**: 暂存/收藏/分类/批量操作/SHA256 查重
- **多端访问**: Desktop (Tkinter) + Web (FastAPI) + CLI + MCP
- **安全沙盒**: `PathValidator` 路径权限注册制 + 符号链接防护

### 2.2 竞品对比矩阵

| 维度 | **FileCortex** | **Repomix** | **Aider (repo map)** | **Cline / Claude Code** | **ripgrep** | **continue.dev** | **MCP Filesystem** | **Sourcegraph** |
|---|---|---|---|---|---|---|---|---|
| **核心方法** | 多模式搜索 + 上下文打包 + 文件操作 | 整仓打包→单文件 | Tree-sitter AST→PageRank→符号图 | Agent 循环：收集→行动→验证 | SIMD 加速正则行搜索 | IDE 插件 + 上下文 provider | 沙盒文件 I/O (MCP stdio) | 三元组索引 + AST 搜索 |
| **文件选择** | smart/exact/regex/content；用户驱动 | gitignore + glob | 依赖图 PageRank 排序 | Agent 自主读取 | glob + gitignore | @提及 + provider | glob search_files | 三元组索引 + SCIP |
| **结构化理解** | 蓝图生成（ASCII 树） | Tree-sitter 压缩（仅签名） | 全符号图：定义+引用+PageRank | 内建于 agent | 无 | provider 可扩展 | 无 | 全 AST/SCIP 跨仓 |
| **Token 预算** | ✅ 估算 + 预警 | ✅ `--token-count-tree` + 压缩 | ✅ 动态 `--map-tokens` 二分 | agent 循环管理 | N/A | 按模型管理 | N/A | N/A |
| **输出格式** | Markdown, XML | XML/MD/JSON/纯文本 | 纯文本符号树 | N/A | JSON/JSONL/文本 | IDE 响应 | 原始文件 | 结构化搜索结果 |
| **安全沙盒** | ✅ PathValidator | secretlint 密钥扫描 | 无（依赖用户判断） | 每工具调用审批 | N/A | 无 | ✅ Roots 白名单 + Docker ro | N/A（只索引） |
| **访问端** | Desktop + Web + CLI + MCP | CLI + Web + Docker + MCP + VSCode | 终端 CLI | VS Code + CLI | CLI | VS Code + JetBrains | stdio MCP | Web + API + Cody + MCP |
| **批量文件操作** | ✅ 重命名/归档/分类/查重 | 无 | 无 | 工具编辑 | 无 | 无 | write/move/create | Batch Changes 跨仓 PR |
| **GitHub Stars** | — | ~26K | ~43K | Cline ~62K | ~65K | ~25K | ~87K（servers） | ~10K |

### 2.3 八大可借鉴学习点

1. **Aider 的 PageRank-on-Symbol-Graph 上下文优先级**
   - Tree-sitter 解析 130+ 语言提取定义/引用 → 有向图 → 个性化 PageRank → 二分法拟合 token 预算
   - **可借鉴**: "smart content search" 结果可按 PageRank 排序；导出时自动纳入高排名依赖文件

2. **ripgrep 的 SIMD + I/O 性能策略**
   - `memchr` 向量化字节扫描、大文件 mmap、目录扫描无锁并行、`RegexSet` 批量 gitignore
   - **可借鉴**: 内容搜索大文件用 `mmap`；`fnmatch` 集合化批量匹配；`os.scandir` + `concurrent.futures` 并行遍历；考虑 PyO3 Rust 后端

3. **Repomix 的 Tree-sitter 压缩是 "压缩导出" 模板**
   - `--compress` 保留函数/类签名 + docstring，剥离实现体，~70% token 削减
   - **可借鉴**: 增加 "structural" 压缩导出模式

4. **MCP Filesystem 的 Roots 沙盒模型**
   - 启动时白名单目录 + 动态 Roots 协议 + Docker `ro` 只读挂载 + 工具注解（`readOnlyHint`/`destructiveHint`）
   - **可借鉴**: 扩展 `PathValidator` 支持 MCP Roots + 工具破坏性注解 + "只读模式"

5. **Cline/Claude Code 的 "Agentic Workspace" 模式 — FileCortex 可做上下文基座**
   - Agent 循环的收集阶段大量消耗 token 遍历目录
   - **可借鉴**: 把搜索 + 打包作为 MCP 一等公民暴露；预索引工作区；SHA256 + 元数据让 agent 知道 "文件未变" 无需重读

6. **Sourcegraph 的 Zoekt 三元组索引是 "规模搜索" 金标准**
   - 默认分支三元组索引 + 非索引分支 grep 兜底 + SCIP 跨仓定义/引用
   - **可借鉴**: 为常搜目录建轻量三元组索引（SQLite FTS5）；后台预索引；频率分析决定索引 vs 原始搜索

7. **continue.dev 的 Context Provider 架构展示模块化**
   - `@docs`/`@issues`/`@git`/`@web`/`@folder`/`@mcp` 标准接口 provider，可组合可配置
   - **可借鉴**: 实现可插拔上下文源架构（搜索结果 provider / 蓝图 provider / 最近文件 provider / git diff provider）

8. **`.contextfile` / `.repomixignore` 模式正成为标准**
   - Repomix `repomix.config.json`、Aider `.aider.conf.yml`、Cline `.claude/rules/`
   - **可借鉴**: 定义 `.filecortex.toml` 项目级配置（搜索 profile / 导出预设 / 忽略模式 / token 预算 / 自定义类别），让配置项目可移植、团队可共享

### 2.4 五大未来趋势信号（2025-2026）

1. **Tree-sitter 代码分块用于 RAG Embedding** — CMU cAST 论文（2025-06）证明 AST 边界分块在 RepoEval +4.3 Recall@5、SWE-bench +2.67 Pass@1。`code-chunk`/`treesitter-chunker`/`unrag` 趋同。
2. **"Context Engineering" 成为独立学科** — Karpathy 命名、Shopify CEO 放大、Google 白皮书、Chroma Research 发现上下文填满后准确率下降。FileCortex 整体价值主张即是 context engineering，应抢占这一定位窗口。
3. **MCP 成为通用集成层** — 9700 万 SDK 下载、1.3 万+ server、Linux Foundation 接管、Gartner 预测 2026 年底 75% API 网关支持 MCP。FileCortex MCP server 必须成为一等公民。
4. **Agentic 文件选择取代手动模式** — Stacklit（250 token 紧凑图）、Codebase-Memory（SQLite 知识图）、Axon（Neo4j 爆炸半径）都在做程序化代码理解。
5. **确定性安全沙盒成为桌面标配** — MCP 漏洞（2026-03 目录逃逸）后行业收敛到 "default deny, explicit allow"。FileCortex 的 `PathValidator` 是竞争优势，应作为安全态势显式文档化。

### 2.5 战略定位建议

**当前格局缺口**: 工具分三阵营 — (a) 无搜索粒度的上下文打包器（Repomix），(b) 无独立上下文导出的 agent 编码工具（Cline/Claude Code），(c) 无 AI 上下文理解的搜索工具（ripgrep/Sourcegraph）。**没有一个能在本地优先 + 搜索 + 上下文工程 + 文件操作 + 安全沙盒 + 离线可用之间统一**。

**建议定位**: *"Your workspace's context engineering control plane. Search. Understand. Export. Operate — all within a security sandbox you control."*

"Orchestration over Collection" 的框架很强：FileCortex 不仅找文件，还理解关系、为 AI 最优打包、执行操作 — 同时尊重 web 原生工具忽略的安全边界。

---

## Part 3: 完整 Code Review 与 BUG 清单

### 3.0 审计基线验证

| 检查项 | 结果 |
|--------|------|
| `python -m ruff check .` | ✅ All checks passed (0 errors) |
| `python -m pytest --collect-only -q` | ✅ 629 tests collected |
| `python -m pytest` | ✅ 629 passed in 195.44s |
| 版本号一致性 (`__init__.py` = `pyproject.toml`) | ✅ 6.5.0 |

### 3.1 BUG 清单 — 按严重度排序

> 以下为 v6.5.0 **全新发现** 的 BUG（V8 报告中已修复的不再列出）。编号规则：`BUG-{层}{序号}`，层 = C(核心) / W(Web·API) / F(前端) / D(部署) / Doc(文档)。

---

#### 🔴 CRITICAL（部署阻断 / 严重安全）

**BUG-D1 [CRITICAL] `pyproject.toml` 打包缺漏 `routers` 包**
- **文件**: `pyproject.toml:50`
- **问题**: `packages = ["file_cortex_core"]`，但 `routers/` 是真实包（有 `__init__.py`，被 `web_app.py` 导入）。`pip install .` 后 `from routers.http_routes import router` 失败 → Web 端完全不可用。
- **影响**: `pip install` 安装版无法启动 Web 服务；仅 `-e` 开发模式可用。
- **修复**:
  ```toml
  [tool.setuptools]
  packages = ["file_cortex_core", "routers"]
  py-modules = ["fctx", "web_app", "file_search", "mcp_server", "build_exe"]
  ```

**BUG-D2 [CRITICAL] `mcp` SDK 未列入依赖，MCP Server 仅以 mock 运行**
- **文件**: `mcp_server.py:21-55`, `requirements.txt`, `pyproject.toml:19-28`
- **问题**: `mcp_server.py` 顶层 `try: from mcp.server.fastmcp import FastMCP except ImportError:` 回退到 mock 类（只 print）。但 `requirements.txt` 与 `pyproject.toml [project.dependencies]` 均无 `mcp`。README 宣称 "MCP Server: AI Agent 原生调用" + 给出 `python mcp_server.py --transport stdio` 命令，但开箱即用只得到 mock 输出。
- **影响**: 核心卖点不可用；用户需手动 `pip install mcp` 但无文档说明。
- **修复**: 在 `pyproject.toml` 新增可选依赖组：
  ```toml
  [project.optional-dependencies]
  mcp = ["mcp>=1.0.0"]
  ```
  并在 README/DEVELOPER_GUIDE 明确：`pip install -e ".[mcp]"` 才能启用真实 MCP 传输。同时为 `mcp_server.py` 的 `run()` 在 `_MCP_SDK_AVAILABLE=False` 时打印明确告警（而非静默 mock）。

**BUG-W1 [CRITICAL] API Token 通过未认证的 index 页泄露**
- **文件**: `web_app.py:116` — `{"api_token": API_TOKEN, ...}` 注入 HTML
- **问题**: `/` 路由无任何认证（`verify_api_token` 中间件仅检查 `/api/` 前缀）。任何能访问服务器的人 `curl http://host:8000/` 即可从 `<script>window.__FCTX_API_TOKEN__ = "..."</script>` 提取 token。由于 `API_TOKEN` 是所有 `/api/*` 端点的**唯一认证门**，整个认证体系形同虚设。
- **影响**: 网络邻接攻击者可获取完整 API 访问权（文件 CRUD、subprocess 执行、项目操作）。
- **修复方案**:
  - 方案 A（推荐）：移除服务端模板注入 token；前端通过认证端点 `GET /api/session/token` 获取（该端点本身可用其他机制如本地 socket 或一次性 TOTP 保护）
  - 方案 B（最小改动）：当 `API_TOKEN` 设置时，`/` 路由也走中间件认证（Basic Auth 或查询参数 token）
  - 配套：前端 `ws_routes.py` 的 token 改用 `Sec-WebSocket-Protocol` 头而非 URL 查询参数（避免日志/Referer 泄露）

**BUG-W2 [CRITICAL] `api_categorize` 缺少源路径安全校验（路径遍历）**
- **文件**: `routers/action_routes.py:172-179`
- **问题**: 其他所有文件操作端点都对每个路径调用 `is_path_safe()`：
  - `api_delete` (fs_routes.py:156-158): `for p in req.paths: if not is_path_safe(p, project_root): raise`
  - `api_rename` (fs_routes.py:100): `if not is_path_safe(req.path, project_root): raise`
  - `api_move` (fs_routes.py:175-176): 每个 src 都 `get_valid_project_root`
  
  但 `api_categorize` **只**校验 `get_valid_project_root(req.project_path, dm)`，然后把 `req.paths` 直接传给 `FileOps.batch_categorize()` → `FileOps.move_file(p_str, target_dir)`。`move_file` (`actions.py:195-217`) 对源路径**无项目边界检查**，只检查 `src_path.exists()`。
- **影响**: 攻击者可移动任意文件（系统文件、其他项目、配置）到项目分类目录。结合其他端点可致数据外泄或破坏。
- **PoC**:
  ```json
  POST /api/actions/categorize
  {
    "project_path": "C:\\registered_project",
    "paths": ["C:\\Windows\\System32\\config\\SAM", "..\\..\\outside.txt"],
    "category_name": "leaked"
  }
  ```
- **修复**:
  ```python
  project_root = get_valid_project_root(req.project_path, dm)
  if not project_root:
      raise HTTPException(status_code=403, detail="Access denied")
  for p in req.paths:
      if not is_path_safe(p, project_root):
          raise HTTPException(status_code=403, detail=f"Path unsafe: {p}")
  moved = FileOps.batch_categorize(req.project_path, req.paths, req.category_name)
  ```

---

#### 🟠 HIGH（重大功能 / 安全）

**BUG-W3 [HIGH] `api_execute_tool` 同步阻塞 subprocess 可耗尽线程池（DoS）**
- **文件**: `routers/action_routes.py:187-252` — `proc.communicate(timeout=300)` 在 sync endpoint
- **问题**: `api_execute_tool` 是同步端点（`def` 非 `async def`），调用 `proc.communicate(timeout=300)` 阻塞线程池 worker 最长 300 秒。FastAPI/Starlette 同步端点默认线程池 `min(32, cpu_count()+4)`（典型 4-8）。攻击者发 8-32 个并发长任务即可耗尽线程池，**所有**同步端点（`get_global_settings`/`get_content`/`api_children` 等）全部挂起。
- **影响**: 8 个并发 exec 请求即可让整个 HTTP API 拒绝服务。
- **修复**: 改为 async + `asyncio.create_subprocess_exec`，或至少用 `await asyncio.to_thread` 包装并以专用受限线程池（独立于全局 anyio 线程池）。

**BUG-W4 [HIGH] WebSocket 搜索 `search_task` 正常完成时不取消（资源泄漏）**
- **文件**: `routers/ws_routes.py:103,110,118`
- **问题**: `websocket_search` 在 line 103 创建 `search_task = asyncio.create_task(asyncio.to_thread(run_search))`。正常完成（收到 `"DONE"`）时 line 110 `break` 退出 while 循环后函数返回，但 `search_task` **从不取消也不 await**。仅在 `WebSocketDisconnect` (line 115) 和通用 `Exception` (line 118) 处取消。
- **影响**: 孤儿后台线程随重复搜索请求累积，缓慢耗尽线程池并泄漏内存；Python 3.12+ 在 GC 时抛 `RuntimeError: Task was destroyed but it is pending!`。
- **对比**: `websocket_action_stream` (line 220-221) 正确使用 `finally: stream_task.cancel()`。
- **修复**: 用 try/finally 包裹搜索循环：
  ```python
  search_task = asyncio.create_task(asyncio.to_thread(run_search))
  try:
      while True:
          res = await websocket.receive_text()
          if res == "DONE":
              break
          # ...
  except WebSocketDisconnect:
      stop_event.set()
  except Exception:
      logger.exception("WS search error")
  finally:
      search_task.cancel()
      with contextlib.suppress(Exception):
          await search_task
  ```

**BUG-W5 [HIGH] ProcessManager PID 复用竞态**
- **文件**: `routers/common.py:47`, `routers/action_routes.py:209-244`
- **问题**: `ProcessManager._processes` 以 OS PID 为键。`register()` 在 line 47 静默覆盖：`self._processes[pid] = proc`。`api_execute_tool` 在 `communicate()` **之前** `register_process(proc.pid, proc)`，在 `finally` 中 `unregister_process(proc.pid)`。期间进程可能退出、PID 被复用，新进程 register 静默覆盖旧条目，旧 Popen 引用泄漏。
- **影响**: 进程引用丢失 → 无法通过 `api_terminate_process` 清理的僵尸进程；若被覆盖 PID 的原进程仍在运行，则成为完全脱离的 detached 进程。
- **修复**:
  ```python
  def register(self, pid: int, proc: subprocess.Popen) -> bool:
      with self._lock:
          if len(self._processes) >= self._max:
              return False
          existing = self._processes.get(pid)
          if existing is not None and existing.poll() is None:
              return False  # PID 仍被活跃进程占用，拒绝
          self._processes[pid] = proc
          return True
  ```

**BUG-F1 [HIGH] mermaid CDN 缺少 SRI integrity 哈希**
- **文件**: `templates/index.html:443`
- **问题**: 所有其他 CDN 资源（Bootstrap、highlight.js、marked、DOMPurify）都有 `integrity` 属性，唯独 mermaid 缺失。供应链攻击向量：CDN 被入侵即可执行恶意 JS 窃取 `window.__FCTX_API_TOKEN__`、文件内容等。
- **影响**: 供应链风险，与 BUG-W1 叠加放大。
- **修复**: 添加 `integrity="sha384-..."`（从 https://www.srijs.org/ 或 `subresource-integrity-tools` 生成）。

**BUG-F2 [HIGH] WebSocket token 以 URL 查询参数传输（日志/Referer 泄露）**
- **文件**: `static/js/state.js:97` — `if (token) params.token = token;`
- **问题**: token 出现在 URL 中 → 服务器访问日志、浏览器历史、`Referer` 头中均会泄露。
- **影响**: token 生命周期外泄。
- **修复**: 改用 `Sec-WebSocket-Protocol` 子协议或先 HTTP 握手换取短期 ticket，再用 ticket 建立 WS。短期可至少：服务器访问日志脱敏 `?token=` 参数。

---

#### 🟡 MEDIUM（功能 / 一致性 / 防御深度）

**BUG-C1 [MEDIUM] `context.py to_xml` 静默吞异常，与 `to_markdown` 不一致**
- **文件**: `file_cortex_core/context.py:229-230`
- **问题**: `to_xml` 文件格式化失败时 `except Exception: pass`（无日志）。而 `to_markdown` 同位置 (line 134-135) 用 `logger.exception(...)`。
- **修复**: 改为 `except Exception: logger.exception("Failed to format %s in XML", full_path)`。

**BUG-C2 [MEDIUM] `archive_selection` 目录 `relative_to` 可能 ValueError**
- **文件**: `file_cortex_core/actions.py:282-317`（目录分支 line 311-316）
- **问题**: 当归档目录不在 `root_dir_p` 下时，`rel_base = root_dir_p if root_dir_p else p.parent`，但 `full_f.relative_to(root_dir_p)` 会因 `full_f` 不在 `root_dir_p` 下而抛 `ValueError`，导致整个归档崩溃。
- **修复**: 目录分支使用与文件分支一致的 `arcname` 决策：
  ```python
  for root, _, files in os.walk(p):
      for file in files:
          full_f = pathlib.Path(root) / file
          if root_dir_p and (root_dir_p == full_f or root_dir_p in full_f.parents):
              arc = full_f.relative_to(root_dir_p)
          else:
              arc = full_f.relative_to(p.parent)
          zipf.write(full_f, arc)
  ```

**BUG-C3 [MEDIUM] Windows 长路径前缀 `\\?\` 被误判为 UNC 拦截**
- **文件**: `file_cortex_core/security.py:56, 162`
- **问题**: `UNC_PREFIXES = ("\\\\", "//")` 和 `normalized_str.startswith("\\\\")` 都会把 `\\?\C:\foo`（Windows 长路径本地前缀，**非 UNC**）误判为 UNC 拒绝。`norm_path` 虽在 line 127-128 剥离 `//?/`，但 `is_safe`/`validate_project` 接收原始 `\\?\` 路径时直接拒绝。
- **影响**: Windows 长路径项目无法注册。
- **修复**: 在 UNC 检查前剥离长路径前缀：
  ```python
  _WIN_LONG_PREFIXES = ("\\\\?\\", "\\?\")
  # is_safe / validate_project 开头：
  for pre in _WIN_LONG_PREFIXES:
      if target_raw.startswith(pre):
          target_raw = target_raw[len(pre):]
          break
  ```

**BUG-C4 [MEDIUM] `batch_rename` 默认 `count=1`（仅替换首处）未文档化**
- **文件**: `file_cortex_core/actions.py:66` — `regex.sub(replacement, p.name, count=1)`
- **问题**: 函数文档未说明 `count=1`。简单替换模式下用户期望替换所有匹配（如 `foo-bar-baz.txt` 中所有 `-`→`_`），实际只得 `foo_bar-baz.txt`。
- **修复**: 增加 `count: int = 1` 参数暴露给调用方，或在 docstring 明确说明；GUI `BatchRenameWindow` 增加 "替换全部 / 仅首处" 选项。

**BUG-C5 [MEDIUM] `SHARED_SEARCH_POOL` 解释器关闭后 submit 抛 RuntimeError**
- **文件**: `file_cortex_core/search.py:28-33`
- **问题**: `atexit` 注册 `shutdown(wait=False, cancel_futures=True)`，但若后台线程在 atexit 后调用 `search_generator`，`SHARED_SEARCH_POOL.submit()` 抛 `RuntimeError: cannot schedule new futures after shutdown`。
- **修复**: `search_generator` 内 submit 前 `if SHARED_SEARCH_POOL._shutdown: return` 提前退出。

**BUG-C6 [MEDIUM] `SearchWorker.run()` 异常静默致线程死亡**
- **文件**: `file_cortex_core/search.py:353-377`
- **问题**: 若 `search_generator` 抛异常（如 BUG-C5），异常从 `run()` 传播，Python `Thread.run()` 静默吞掉线程异常，worker 死亡但无 error 入队，UI 轮询队列永远等不到结果。
- **修复**: `run()` 用 try/except 包裹，异常时 `self.result_queue.put({"error": str(e)})` 通知 UI。

**BUG-W6 [MEDIUM] `api_terminate_process` PID TOCTOU（可能杀错进程）**
- **文件**: `routers/action_routes.py:258-276`
- **问题**: 先 `process_manager.get(req.pid)` 取 Popen，再 `terminate_process(req.pid)` 按 PID 杀。期间进程可能退出、PID 被复用，`terminate_process` 杀错无关系统进程。错误兜底 `os.kill(req.pid, SIGTERM)` 同样无所有权检查。
- **修复**: 用 Popen 对象而非 PID 终止：
  ```python
  proc = process_manager.get(req.pid)
  if not proc or proc.poll() is not None:
      return {"status": "error", "msg": "Process not found or finished"}
  terminate_process(proc.pid)  # 或直接 proc.terminate()
  ```

**BUG-W7 [MEDIUM] 多个 `list[str]` 字段无 `max_length`（无界 body 攻击）**
- **文件**: `routers/schemas.py:27,47,75,181,195,203`
- **问题**: 仅 `FileSaveRequest.content` 有 `max_length=10_000_000`。`GenerateRequest.files`/`FileDeleteRequest.paths`/`FileArchiveRequest.paths`/`CategorizeRequest.paths`/`ToolExecuteRequest.paths`/`BatchRenameRequest.paths` 均为裸 `list[str]`。
- **影响**: 攻击者发 1000 万空字符串（~80MB JSON）→ 反序列化耗数百 MB 内存。
- **修复**: 全部加 `Field(..., max_length=1000)`；并在 FastAPI app 设置 `max_request_size`。

**BUG-W8 [MEDIUM] `FileSaveRequest` 缺 `project_path` 字段，API 设计不一致**
- **文件**: `routers/schemas.py:57-61`, `routers/fs_routes.py:210-224`
- **问题**: 其他所有 mutation 端点（delete/rename/create/move/archive/categorize）都显式带 `project_path` 唯一定位项目；`api_save` 只用 `path` 推断项目根。若两项目路径前缀重叠，可能解析到错误项目。
- **修复**: `FileSaveRequest` 加 `project_path: str`，`api_save` 一致性校验。

**BUG-W9 [MEDIUM] `NoteRequest.note` 等多字段无长度上限（磁盘耗尽）**
- **文件**: `routers/schemas.py:96-98,135,142,149,156`
- **问题**: `note: str` 无 `max_length`；`SessionRequest.data`/`ProjectSettingsRequest.settings`/`ToolsUpdateRequest.tools`/`CategoriesUpdateRequest.categories` 为 `dict[str, Any]` 无界。这些写入 `config.json` 无大小检查。
- **影响**: 认证攻击者可反复发大 blob 致磁盘耗尽。
- **修复**: 所有 string 加 `Field(max_length=...)`；dict 字段加自定义 size-aware validator。

**BUG-W10 [MEDIUM] API Token 比较使用 `==`（时序侧信道）**
- **文件**: `web_app.py:58` — `if token != API_TOKEN`; `routers/ws_routes.py:31` — `token == expected_token`
- **问题**: 简单字符串比较是时序侧信道，理论上可暴力破解 token。
- **修复**: 改用 `hmac.compare_digest(token, API_TOKEN)`。

**BUG-F3 [MEDIUM] 工具执行 WebSocket 在模态框关闭时不清理（资源泄漏）**
- **文件**: `static/js/main.js:756-841`
- **问题**: `executeToolOnStaged` 为每个文件创建 WebSocket（局部变量，非 `App.state.socket`）。用户关闭 `toolResultModal` 时，`.then(() => runNext(index+1))` 链继续，对隐藏 DOM 创建更多 WebSocket 并附加输出。socket 从不显式关闭。
- **修复**: 监听 modal `hidden.bs.modal` 事件，设置取消标志位，`runNext` 检查后中止链。

**BUG-F4 [MEDIUM] `ctxAction` 失败时 `currentFile` 全局状态污染**
- **文件**: `static/js/main.js:1244-1262`
- **问题**: `ctxAction('fav')` 临时把 `App.state.currentFile` 改为 `state.contextPath`，调用 `addToFavorites`，完成后恢复。若 `addToFavorites` 抛错（API 失败），`savedFile` 赋值不执行，`currentFile` 停留在错误路径。`ctxAction('delete')` 同。
- **修复**: 用 try/finally 保证恢复：
  ```javascript
  const savedFile = App.state.currentFile;
  App.state.currentFile = App.state.contextPath;
  try { await App.addToFavorites(); }
  finally { App.state.currentFile = savedFile; }
  ```

**BUG-F5 [MEDIUM] `syncStagingToBackend` 项目切换后用旧 staging 发新项目**
- **文件**: `static/js/main.js:900-911`
- **问题**: debounced `syncStagingToBackend` 在执行时读取 `App.state.projectPath`（引用）。若 500ms 内用户切换项目且 `openProject` 在 API 失败前已设 `projectPath`（line 186）但未替换 `staging`（line 214 未到），定时器触发时把旧 staging 写到新失败项目。
- **修复**: debounce 捕获调用时的 `projectPath` 快照，执行时校验未变才发；或 `openProject` 失败时回滚 `projectPath`。

**BUG-F6 [MEDIUM] 文件树渲染 `mtime_fmt`/`size_fmt` 未转义直接 innerHTML**
- **文件**: `static/js/ui.js:337-341`
- **问题**: `node.mtime_fmt || ''` 和 `metaInfo`（含 `node.size_fmt`）未走 `escapeHtml`。虽当前来自后端格式化函数（安全字符串），但任何后端变更或存储污染即成 XSS。防御深度违规。
- **修复**: 全部走 `escapeHtml(node.mtime_fmt || '')`。

**BUG-F7 [MEDIUM] 50+ 内联 `onclick`/`onchange` 阻碍 CSP 落地**
- **文件**: `templates/index.html`（全文）
- **问题**: 无 CSP meta 标签；大量内联事件处理器使 `script-src 'self'` 无法实施。与 BUG-F1（mermaid 无 SRI）叠加放大风险。
- **修复**: 长期迁移到 `addEventListener`；短期至少加 CSP `script-src 'self' 'unsafe-inline'` 限制外部域。

**BUG-F8 [MEDIUM] `showActionModal`/`closeActionModal` 确认按钮禁用竞态**
- **文件**: `static/js/main.js:127-138`, `static/js/ui.js:232-238`
- **问题**: `actionConfirm` 点击后 `disabled = true`，`finally` 恢复。若 handler 内调用 `closeActionModal()` 后立即 `showActionModal()`（嵌套），新模态框的确认按钮仍 disabled（旧 finally 未跑）。
- **修复**: `closeActionModal` 内显式 `actionConfirm.disabled = false`。

---

#### 🟢 LOW（健壮性 / 体验）

**BUG-C7 [LOW] `is_safe`/`validate_project` TOCTOU（理论性）**
- **文件**: `file_cortex_core/security.py:70-73`
- 问题: `Path.resolve()` 解析符号链接与后续文件操作之间存在窗口期，符号链接可被替换。理论漏洞，难实战利用。

**BUG-C8 [LOW] `read_text_smart` 缓存键用 `file_path.absolute()` 非全解析**
- **文件**: `file_cortex_core/file_io.py:394-396`
- 问题: 缓存键未 `resolve()`，符号链接不同路径指向同文件会重复缓存。功能正确，仅缓存效率问题。

**BUG-C9 [LOW] `terminate_process` Windows `taskkill` 非零退出码静默忽略**
- **文件**: `file_cortex_core/process_utils.py:18-22`
- 问题: `subprocess.run` 不检查 returncode，进程已死时 taskkill 错误被吞。设计为 best-effort，可接受。

**BUG-F9 [LOW] `token_threshold = 0` 被当作未设置**
- **文件**: `static/js/main.js:984` — `|| ` 短路
- 问题: 用户设 0 时被默认值 128000 覆盖。

**BUG-F10 [LOW] 剪贴板 API 在 HTTP 非 localhost 失败**
- **文件**: `static/js/main.js:1023`
- 问题: `navigator.clipboard.writeText` 需 HTTPS 或 localhost；HTTP 部署时静默失败，无 `execCommand('copy')` 兜底。

**BUG-F11 [LOW] WebSocket `onerror` nulling socket 但无 `onclose`**
- **文件**: `static/js/main.js:712-717`
- 问题: `onerror` 设 `App.state.socket = null` 但无 `onclose` 处理；正常关闭时引用残留。

**BUG-F12 [LOW] `__FCTX_API_TOKEN__` 全局变量对 XSS/扩展暴露**
- **文件**: `templates/index.html:439`
- 问题: 任何 XSS 或被入侵的 CDN 脚本可读 token。与 BUG-W1/F1 联动放大。

**BUG-F13 [LOW] `searchOverlay` 缺 ARIA role**
- **文件**: `templates/index.html:75-81`
- 问题: 无 `role="dialog"`/`aria-modal="true"`，屏幕阅读器不感知。

---

#### 📘 DOC（文档一致性）

**BUG-Doc1 [LOW] `TECHNICAL_GUIDE.md` 测试数过时（597 vs 629）**
- **文件**: `TECHNICAL_GUIDE.md` 第 5.1 节
- 问题: 多处仍写 "597 项测试"，实际 629。

**BUG-Doc2 [LOW] `TECHNICAL_GUIDE.md` / `DEVELOPER_GUIDE.md` 引用已合并的测试文件**
- **文件**: 两份 guide 第 5/6 节
- 问题: 仍列 `test_web_endpoints.py`/`test_web_api_advanced.py`/`test_api_v6.py`（TC-2 已合并入 `test_web_api.py`）。

**BUG-Doc3 [LOW] `DEVELOPER_GUIDE.md` 7.0 变更摘要 "597 tests" 过时**
- **文件**: `DEVELOPER_GUIDE.md:210`

**BUG-Doc4 [LOW] README MCP 命令缺前置依赖说明**
- **文件**: `README.md:91-92`
- 问题: `python mcp_server.py --transport stdio` 未说明需 `pip install mcp`（见 BUG-D2）。

**BUG-Doc5 [LOW] `pyproject.toml [project.scripts]` 缺 `fctx-mcp` 入口**
- **文件**: `pyproject.toml:45-47`
- 问题: 仅声明 `fctx`/`fctx-web`，无 MCP server 控制台脚本，与"多端访问"卖点不一致。

---

### 3.2 一致性与健康性检查

| 检查项 | 状态 | 说明 |
|--------|------|------|
| 版本号一致性 | ✅ | `__init__.py` = `pyproject.toml` = 6.5.0 |
| 前后端参数对齐 | ✅ | token_threshold/preview_limit_mb/api_token/wsSearch/wsExecute 全对齐 |
| Python 类型标注 | ⚠️ | 公共 API 完整；`file_search.py` 部分内部方法缺 |
| 错误处理覆盖 | ⚠️ | 核心层良好（BUG-C1 除外）；GUI 层部分 bare except |
| 线程安全 | ⚠️ | DataManager._lock 正确；ProcessManager PID 复用见 BUG-W5 |
| 测试覆盖 | ⚠️ | 629 通过；GUI/E2E/零断言测试见附录 B |
| 安全沙盒 | ⚠️ | PathValidator 强；但 BUG-W1/W2 两处 CRITICAL 绕过 |
| 原子写入 | ✅ | config.save() + FileOps.save_content() 均用 tempfile + os.replace |
| 打包完整性 | ❌ | BUG-D1 routers 包缺漏；`pip install .` 不可用 |
| 部署就绪度 | ❌ | BUG-D2 MCP 依赖缺；mock 回退不可用 |

---

## Part 4: 落地评估与执行计划

### 4.1 当前完成度评估

| 子系统 | 完成度 | 缺失 |
|--------|--------|------|
| 核心搜索 | 90% | BUG-C5/C6 健壮性；增量索引；文件指纹缓存 |
| 上下文导出 | 85% | BUG-C1 静默；流式导出；tree-sitter 压缩模式 |
| 文件操作 | 90% | BUG-C2 归档；BUG-C4 rename count；撤销栈 (Undo) |
| 配置管理 | 95% | 迁移版本号；BUG-W9 字段上限 |
| Web 前端 | 75% | BUG-F1/F3/F4/F5/F6/F7；虚拟滚动；E2E 测试；CSP |
| Desktop GUI | 80% | 组件拆分；主题切换；零测试覆盖 |
| MCP Server | 40% | BUG-D2 mock 回退；需真实 stdio；工具注解 |
| CLI | 90% | 已有 search/export；可加 categorize/dedupe |
| 安全 | 65% | BUG-W1/W2 CRITICAL；token 时序；rate limiting |
| 测试 | 70% | GUI 零测试；55+ 零断言；E2E 缺失；118s sleep 拖累 |
| 打包/部署 | 50% | BUG-D1/D2 阻断；CI 无 Windows runner |

**总体部署就绪度**: 70%。**核心阻断项**为 BUG-D1（打包）、BUG-D2（MCP 依赖）、BUG-W1（token 泄露）、BUG-W2（路径遍历）。修复这 4 项后即可称为"实际可落地"。

### 4.2 执行计划 — 四阶段递进

#### Phase P0：部署阻断修复（必修，方能"实际可落地"）

| # | 文件 | 修改 | BUG | 预计 |
|---|------|------|-----|------|
| P0.1 | `pyproject.toml:50-51` | `packages` 加 `routers`；`py-modules` 加 `mcp_server`、`build_exe` | D1 | 5 min |
| P0.2 | `pyproject.toml` `[project.optional-dependencies]` | 加 `mcp = ["mcp>=1.0.0"]`；`README.md:91-92` 加安装说明 | D2 | 10 min |
| P0.3 | `pyproject.toml:45-47` | `[project.scripts]` 加 `fctx-mcp = "mcp_server:main"` | D2/Doc5 | 2 min |
| P0.4 | `routers/action_routes.py:172-179` | `api_categorize` 加 `for p in req.paths: is_path_safe(p, project_root)` | W2 | 10 min |
| P0.5 | `web_app.py:108-120` | `/` 路由：`API_TOKEN` 设置时返回登录页或要求 Basic Auth；移除 HTML 内 token 注入 | W1 | 30 min |
| P0.6 | `templates/index.html:443` | mermaid 加 `integrity="sha384-..."` | F1 | 5 min |
| P0.7 | `mcp_server.py:46-54` | `_MCP_SDK_AVAILABLE=False` 时 `run()` 打印明确告警 + 退出码 1 | D2 | 5 min |

**验证**: `pip install .` 成功；`python web_app.py` 启动；`curl /` 不再泄露 token；`api_categorize` 拒绝越界路径；mermaid SRI 校验通过。

#### Phase P1：安全加固与一致性（高优先）

| # | 文件 | 修改 | BUG |
|---|------|------|-----|
| P1.1 | `routers/schemas.py` 全文 | 所有 `list[str]` 加 `Field(..., max_length=1000)`；`note` 加 `max_length=10000`；dict 字段加 size validator | W7/W9 |
| P1.2 | `web_app.py:58`, `routers/ws_routes.py:31` | token 比较改 `hmac.compare_digest` | W10 |
| P1.3 | `routers/ws_routes.py:103-118` | `search_task` 用 try/finally 取消 | W4 |
| P1.4 | `routers/common.py:43-50` | `register()` 检查 existing.poll() | W5 |
| P1.5 | `routers/action_routes.py:258-276` | `api_terminate_process` 用 Popen 而非 PID | W6 |
| P1.6 | `routers/action_routes.py:187-252` | `api_execute_tool` 改 `async` + `asyncio.create_subprocess_exec` 或专用线程池 | W3 |
| P1.7 | `routers/schemas.py:57`, `routers/fs_routes.py:210` | `FileSaveRequest` 加 `project_path` | W8 |
| P1.8 | `file_cortex_core/context.py:229-230` | `to_xml` 加 `logger.exception` | C1 |
| P1.9 | `file_cortex_core/actions.py:311-316` | `archive_selection` 目录分支 arcname 一致 | C2 |
| P1.10 | `file_cortex_core/security.py:56,162` | UNC 检查前剥离 `\\?\` 长路径前缀 | C3 |
| P1.11 | `file_cortex_core/actions.py:66` | `batch_rename` 加 `count` 参数 + docstring | C4 |
| P1.12 | `file_cortex_core/search.py:264` | submit 前 `_shutdown` 检查 | C5 |
| P1.13 | `file_cortex_core/search.py:353-377` | `SearchWorker.run` try/except 入队 error | C6 |
| P1.14 | `static/js/state.js:97` | WS token 改 `Sec-WebSocket-Protocol`（或访问日志脱敏作短期） | F2 |
| P1.15 | `static/js/main.js:756-841` | `executeToolOnStaged` 监听 modal hide 中止链 | F3 |
| P1.16 | `static/js/main.js:1244-1262` | `ctxAction` try/finally 恢复 currentFile | F4 |
| P1.17 | `static/js/main.js:900-911` | debounce 捕获 projectPath 快照 | F5 |
| P1.18 | `static/js/ui.js:337-341` | `mtime_fmt`/`size_fmt` 走 escapeHtml | F6 |

#### Phase P2：测试补强（覆盖加固，见附录 B）

| # | 文件 | 内容 |
|---|------|------|
| P2.1 | `tests/conftest.py:61` | `time.sleep(0.2)` → 条件化或降至 0.05s（省 ~100s/全量） |
| P2.2 | 新建 `tests/test_security_v9.py` | W1/W2/W6 回归 + W7/W9 输入上限 + W10 时序 |
| P2.3 | 新建 `tests/test_gui_modules.py` | mock tkinter 测 BatchRename/DuplicateFinder/PathCollection |
| P2.4 | 新建 `tests/test_search_unit.py` | `SearchQuery`/`PathMatcher`/`ContentMatcher` 单元隔离 |
| P2.5 | 新建 `tests/test_e2e_scenarios.py` | 3-5 条端到端（open→search→stage→export→categorize） |
| P2.6 | 全测试文件 | 修 55+ 零断言测试；移除 5 处 `or "Error" in result` |
| P2.7 | `tests/test_bugfix_v633.py` | 去除 `list(projects.keys())[0]` 顺序依赖 |
| P2.8 | 新建 `tests/test_packaging.py` | `pip install .` 烟雾测试（import routers/web_app） |

#### Phase P3：架构演进（v7.0 路线图）

| 主题 | 内容 | 来源 |
|------|------|------|
| `.filecortex.toml` 项目配置 | 搜索 profile / 导出预设 / token 预算 / 自定义类别，团队可共享 | 学习点 8 |
| Tree-sitter 压缩导出 | 保留签名剥离实现体，~70% token 削减 | 学习点 3 / 趋势 1 |
| PageRank 上下文优先级 | 智能导出按依赖图排名自动纳入相关文件 | 学习点 1 |
| MCP 一等公民 | 每个主模式暴露 MCP 工具 + Roots 协议 + 工具破坏性注解 | 学习点 4 / 趋势 3 |
| 插件化上下文源 | 标准 provider 接口（搜索/蓝图/最近/git diff） | 学习点 7 |
| 轻量三元组索引 | SQLite FTS5 后台预索引常搜目录 | 学习点 6 |
| 前端虚拟滚动 + 拖拽 | 万级文件树；Staging 拖拽 | ROADMAP v7.0 |
| CSP 落地 | 移除内联事件处理器 | BUG-F7 |
| CI Windows runner | `.github/workflows/test.yml` matrix 加 `windows-latest` | 当前缺 |
| 速率限制 | slowapi 中间件保护 `/api/*` | ROADMAP v7.0 |

### 4.3 执行顺序与依赖

```
Phase P0 (部署阻断, ~1-2 小时)
  ├─ P0.1-P0.3 打包修复 (独立)
  ├─ P0.4 api_categorize (独立)
  ├─ P0.5 token 泄露 (独立, 但影响前端需联动)
  ├─ P0.6 mermaid SRI (独立)
  └─ P0.7 MCP 告警 (独立)
      ↓ 验证：pip install / web 启动 / curl / 端到端 categorize
Phase P1 (安全加固, ~4-6 小时, 可并行)
  ├─ P1.1-P1.2 输入上限 + 时序 (schemas/web_app/ws)
  ├─ P1.3-P1.6 进程/线程/异步 (ws_routes/common/action_routes)
  ├─ P1.7 保存接口一致 (schemas/fs_routes)
  ├─ P1.8-P1.13 核心健壮性 (context/actions/security/search)
  └─ P1.14-P1.18 前端健壮性 (state/main/ui)
      ↓ 验证：全量回归 + 新增 P2.2 安全测试
Phase P2 (测试补强, 持续)
  ├─ P2.1 立即：删 sleep → 全量从 195s 降至 ~80s
  ├─ P2.6/P2.7 立即：修零断言 + 顺序依赖
  └─ P2.2-P2.5/P2.8 新建测试文件
      ↓
Phase P3 (架构演进, v7.0 季度级)
```

### 4.4 单元测试设计原则（v9 测试补强）

1. **AAA 模式**: Arrange / Act / Assert，每测试必含明确 assert
2. **零容忍**: 不允许 `"Error" in result` 这类宽松通过
3. **隔离**: 通过 fixture 注入，禁用 `list(dict.keys())[0]` 全局顺序依赖
4. **覆盖矩阵**: 每个公共函数至少 1 happy + 2 edge + 1 error
5. **GUI 可测**: mock tkinter（`tkinter.Tk` 用 `MagicMock`），测纯逻辑方法（`update_preview`/`smart_select`/`delete_selected`）
6. **E2E 黄金路径**: open → search → stage → note/tag → stats → export XML → 验证输出含搜索结果
7. **安全回归**: 每个 BUG-Wx 修复配 1 条 PoC 测试（如 BUG-W2 配 `paths` 含 `..` 的请求）

详细测试用例见附录 B。

---

## 附录 A: 修改位置索引

| 文件 | 行号 | BUG/Phase | 修改类型 |
|------|------|-----------|----------|
| `pyproject.toml` | 45-47, 50-51 | D1/D2/Doc5 | 打包包/可选依赖/脚本 |
| `requirements.txt` | — | D2 | 补 `mcp` 注释或留空（用可选组） |
| `README.md` | 91-92 | Doc4 | MCP 安装说明 |
| `mcp_server.py` | 46-54 | D2 | mock 回退加告警 |
| `web_app.py` | 58, 108-120 | W1/W10 | token 泄露 + 时序 |
| `routers/schemas.py` | 27,47,57,75,96,135,142,149,156,181,195,203 | W7/W8/W9 | Field 上限 + project_path |
| `routers/fs_routes.py` | 210-224 | W8 | api_save 用 project_path |
| `routers/action_routes.py` | 172-179, 187-252, 258-276 | W2/W3/W6 | categorize 校验/async exec/Popen 终止 |
| `routers/ws_routes.py` | 31, 103-118 | W4/W10 | task 取消 + 时序 |
| `routers/common.py` | 43-50 | W5 | register PID 复用检查 |
| `file_cortex_core/context.py` | 229-230 | C1 | logger.exception |
| `file_cortex_core/actions.py` | 66, 311-316 | C2/C4 | archive arcname + rename count |
| `file_cortex_core/security.py` | 56, 162 | C3 | 长路径前缀剥离 |
| `file_cortex_core/search.py` | 264, 353-377 | C5/C6 | shutdown 检查 + run 异常入队 |
| `templates/index.html` | 443, 全文 | F1/F7 | mermaid SRI + 内联事件迁移 |
| `static/js/state.js` | 97 | F2 | WS token 头 |
| `static/js/main.js` | 127-138, 756-841, 900-911, 984, 1023, 1244-1262 | F3-F5/F8-F10 | 多项前端 |
| `static/js/ui.js` | 232-238, 337-341 | F6/F8 | escape + 按钮禁用 |
| `TECHNICAL_GUIDE.md` | 第 5.1 节 | Doc1/Doc2 | 629 + 移除已合并文件 |
| `DEVELOPER_GUIDE.md` | 第 6/7 节 | Doc2/Doc3 | 同上 |
| `tests/conftest.py` | 61 | P2.1 | sleep 条件化 |
| `tests/test_bugfix_v633.py` | 29,50,186,201 | P2.7 | 去顺序依赖 |
| 新建 `tests/test_security_v9.py` | — | P2.2 | W1/W2/W6/W7/W9/W10 回归 |
| 新建 `tests/test_gui_modules.py` | — | P2.3 | mock tkinter |
| 新建 `tests/test_search_unit.py` | — | P2.4 | 搜索类单元 |
| 新建 `tests/test_e2e_scenarios.py` | — | P2.5 | 端到端 |
| 新建 `tests/test_packaging.py` | — | P2.8 | pip install 烟雾 |

---

## 附录 B: 测试补强计划

### B.1 现状（v6.5.0 基线）

- **629 测试通过**（pytest 实测；AST 静态计数 590 因 parametrize 差异，非真实缺口）
- **核心模块覆盖良好**: config / security / file_io / actions / search / context / duplicate / format_utils / process_utils
- **关键盲区**:
  - tkinter GUI（3 模块 ~22KB）**零测试**
  - 无浏览器 E2E（Playwright/Cypress）
  - **55+ 测试零 assert**（仅靠"不抛异常"通过）
  - 5 处 `"Error" in result` 宽松通过
  - `conftest.py:61` `time.sleep(0.2)` × 629 = ~118s 全量拖累
  - `routers/schemas.py` 26 个 Pydantic 模型无直接验证测试
  - `SearchQuery`/`PathMatcher`/`ContentMatcher` 无单元隔离测试

### B.2 覆盖矩阵（核心模块）

| 模块 | 覆盖 | 备注 |
|------|------|------|
| `config.py` DataManager (28 方法) | ✅ 良好 | 3 个私有方法（`_init_data`/`_setup_logging`/`_get_config_file`）未直测 |
| `security.py` PathValidator | ✅ 优秀 | 参数化矩阵 + 边界 |
| `file_io.py` FileUtils | ✅ 良好 | `_detect_encoding`/`_get_cached_gitignore_spec`/`clear_cache` 缺直测 |
| `search.py` | ⚠️ 部分 | `search_generator` 好；`SearchQuery`/`PathMatcher`/`ContentMatcher` 无单元 |
| `actions.py` | ✅ 良好 | `_validate_item_name`/`win_quote` 缺直测 |
| `context.py` | ✅ 良好 | |
| `duplicate.py` | ✅ 良好 | `_get_hash` 间接 |
| `format_utils.py` | ✅ 良好 | |
| `process_utils.py` | ✅ 良好 | |
| **GUI (tkinter)** | ❌❌ 零 | 3 模块完全未测 |
| `routers/schemas.py` | ❌ 缺 | 26 模型仅隐式 |
| WebSocket 协议 | ⚠️ 薄 | 1 条搜索流；缺压测/断连/超时 |

### B.3 新增测试用例设计

#### `tests/test_security_v9.py`（P2.2，预计 15-20 项）

```python
class TestApiCategorizeTraversal:
    """BUG-W2 回归。"""
    def test_categorize_rejects_path_outside_project(self, project_client, mock_project):
        """越界路径被 403 拒绝。"""
        # PoC: paths 含 mock_project 父目录文件
    def test_categorize_rejects_dotdot_traversal(self, project_client, mock_project):
        """../ traversal 被拦截。"""
    def test_categorize_accepts_valid_within_project(self, project_client, mock_project):
        """项目内合法路径正常分类。"""

class TestApiTokenSecurity:
    """BUG-W1/W10 回归。"""
    def test_index_page_does_not_leak_token_when_set(self, api_client, monkeypatch):
        """API_TOKEN 设置时 GET / 不含 token。"""
    def test_token_compare_is_constant_time(self):
        """hmac.compare_digest 被使用（通过时序或源码扫描）。"""
    def test_ws_token_query_param_not_logged(self):
        """访问日志脱敏 ?token=（可选）。"""

class TestInputSizeLimits:
    """BUG-W7/W9 回归。"""
    def test_generate_rejects_files_list_over_1000(self, project_client):
        """超过 max_length 返回 422。"""
    def test_save_rejects_content_over_10mb(self, project_client):
    def test_note_rejects_over_max_length(self, project_client):

class TestProcessManagerPidReuse:
    """BUG-W5 回归。"""
    def test_register_refuses_when_pid_still_live(self):
        """existing.poll() is None 时拒绝覆盖。"""
    def test_terminate_uses_popen_not_raw_pid(self):
        """BUG-W6：终止前确认 Popen 一致。"""
```

#### `tests/test_gui_modules.py`（P2.3，预计 12-15 项）

```python
@pytest.fixture
def mock_tk(monkeypatch):
    """Mock tkinter 全家桶。"""
    monkeypatch.setattr('tkinter.Tk', MagicMock)
    monkeypatch.setattr('tkinter.Toplevel', MagicMock)
    # ...

class TestBatchRenameLogic:
    """测纯逻辑，不测 UI 渲染。"""
    def test_update_preview_valid_regex(self, mock_tk):
    def test_update_preview_invalid_regex_shows_error(self, mock_tk):
    def test_execute_rename_conflict_rollback(self, mock_tk):
    def test_count_param_respected(self, mock_tk):  # BUG-C4 回归

class TestDuplicateFinderSmartSelect:
    def test_smart_select_keep_earliest(self, mock_tk):
        """保留最早 mtime。"""
    def test_smart_select_keep_latest(self, mock_tk):
    def test_smart_select_empty_tree_noop(self, mock_tk):  # BUG-8 v8 回归
    def test_smart_select_missing_mtime_value(self, mock_tk):

class TestPathCollectionPresets:
    def test_on_preset_select_switches_mode(self, mock_tk):
    def test_do_copy_and_close_output_format(self, mock_tk):
```

#### `tests/test_search_unit.py`（P2.4，预计 10-12 项）

```python
class TestPathMatcher:
    """单元隔离测试，不依赖 walk_filtered。"""
    @pytest.mark.parametrize("mode,query,path,expected", [
        ("smart", "main", "src/main.py", True),
        ("smart", "main test", "src/main.py", False),  # 必须全包含
        ("exact", "main", "src/main.py", True),
        ("regex", r"\.py$", "a.py", True),
        ("smart", "-test", "test_main.py", False),  # 负向
    ])
    def test_matches_matrix(self, mode, query, path, expected):
        matcher = PathMatcher(SearchQuery(query=query, mode=mode))
        assert matcher.matches(path) is expected

class TestContentMatcher:
    def test_match_file_binary_skipped(self, tmp_path):
    def test_match_file_max_bytes_enforced(self, tmp_path):
    def test_match_file_encoding_gbk(self, tmp_path):
    def test_match_file_case_sensitive(self, tmp_path):

class TestSearchQuery:
    def test_default_max_results(self):
    def test_invalid_regex_raises(self):
```

#### `tests/test_e2e_scenarios.py`（P2.5，预计 5 项）

```python
class TestGoldenPath:
    """open → search → stage → note/tag → stats → export → 验证。"""
    def test_full_workflow_xml_export(self, project_client, mock_project):
        # 1. open
        # 2. search 'main' smart mode
        # 3. stage 结果
        # 4. add note + tag
        # 5. stats 返回 token 估算
        # 6. POST /api/generate format=xml
        # 7. assert '<context>' in result and 'main.py' in result

    def test_batch_rename_archive_delete_cycle(self, project_client, mock_project):
    def test_session_persistence_roundtrip(self, project_client, mock_project):
    def test_large_project_100_files_performance(self, project_client, stress_project):
    def test_search_interrupt_and_resume(self, project_client, mock_project):

class TestCategorizeWorkflow:
    """含 BUG-W2 安全回归。"""
    def test_categorize_then_archive(self, project_client, mock_project):
    def test_categorize_rejects_outside_paths(self, project_client, mock_project):
```

#### `tests/test_packaging.py`（P2.8，预计 3 项）

```python
class TestPackagingIntegrity:
    """BUG-D1 回归。"""
    def test_routers_importable(self):
        import routers  # noqa: F401
    def test_web_app_importable(self):
        import web_app  # noqa: F401
    def test_pyproject_packages_includes_routers(self):
        import tomllib
        with open('pyproject.toml','rb') as f:
            assert 'routers' in tomllib.load(f)['tool']['setuptools']['packages']
```

### B.4 零断言测试修复清单（P2.6，节选）

需补 assert 的代表测试（共 55+，跨 11 文件）：
- `test_comprehensive_v63.py:28` `test_cli_open_existing_path` — 仅调用无 assert
- `test_comprehensive_v63.py:92,175,193,211,228` — `or "Error" in result` 宽松
- `test_comprehensive_v63.py:312,331` — `assert x >= 0` 永真
- `test_bugfix_v7.py` 多处 `pytest.raises` 未匹配 message
- `test_web_api.py:173` `test_api_archive` — 仅查 200，未验证 zip 内容

修复原则：每个测试至少 1 条行为断言（返回值/文件系统状态/错误消息匹配）。

### B.5 性能优化（P2.1 立即收益）

`tests/conftest.py:61` 的 `time.sleep(0.2)` 在 Windows 每个测试执行。629 × 0.2s = **125s 纯睡眠**（占全量 195s 的 64%）。

**建议**:
1. 先尝试删除 sleep，跑全量若通过则保留删除
2. 若个别测试需等待文件锁，改为按需（fixture 参数化 `needs_fs_sync`）
3. 或降至 0.05s（省 ~115s，全量降至 ~80s）

---

## 总结

FileCortex v6.5.0 在工程规范（Ruff 0、Google Style、629 测试、Pydantic V2、OOM 保护）上已达到**优秀水平**，但在**部署就绪度（70%）**上仍存 4 项阻断：

- BUG-D1 打包缺漏 `routers` → `pip install .` 不可用
- BUG-D2 MCP 依赖缺失 → 核心卖点 mock-only
- BUG-W1 token 经未认证页泄露 → 认证形同虚设
- BUG-W2 `api_categorize` 路径遍历 → 任意文件移动

修复 Phase P0（~1-2 小时）即可达到"实际可落地"。Phase P1（~4-6 小时）补齐安全加固与一致性。Phase P2（持续）补强测试覆盖至"全方位验证"。Phase P3（季度级）按 v7.0 路线图向"Context Engineering 控制平面"定位演进，重点投资 tree-sitter 压缩、PageRank 上下文、MCP 一等公民、插件化 provider、轻量索引。

**战略窗口**: "Context Engineering" 概念已被 Karpathy 命名并获业界共识，但尚无产品占据该定位。FileCortex 的"本地优先 + 搜索 + 上下文打包 + 文件操作 + 安全沙盒"五合一组合在竞品空白区，配合 `.filecortex.toml` 项目可移植配置 + 真实可用的 MCP server，有窗口期成为该品类的定义性产品。

---

*审计: Sisyphus (OhMyOpenCode) | 5 并行 subagent + 主审计复核 | 2026-06-15*
