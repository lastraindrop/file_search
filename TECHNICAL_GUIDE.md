# FileCortex 技术指南 — 架构、参数对齐与测试策略

> **版本**: 6.5.0 | **测试**: 597 passed | **日期**: 2026-05-29 | **Ruff**: 0 errors | **Google Style**: 全规范审计完成

本文档面向 FileCortex 开发者和维护者，详细阐述系统的核心架构、参数动态对齐机制、
常见 BUG 模式与预防策略，以及测试架构设计。

---

## 1. 系统架构

### 1.1 分层模型

```
┌───────────────────────────────────────────────────────────────┐
│  Entry Points (4)                                              │
│  ┌─────────┐ ┌──────────────┐ ┌──────┐ ┌─────────────────┐    │
│  │ Desktop │ │ Web (FastAPI) │ │ CLI  │ │ MCP Server      │    │
│  │tkinter  │ │ REST + WS     │ │fctx  │ │ FastMCP         │    │
│  │ main()  │ │ uvicorn       │ │main()│ │ get_mcp().tool()│    │
│  └────┬────┘ └──────┬───────┘ └──┬───┘ └───────┬─────────┘    │
│       │              │            │              │              │
├───────┴──────────────┴────────────┴──────────────┴────────────┤
│  Route Layer (routers/)                                        │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────┐        │
│  │project_routes│ │ fs_routes    │ │ action_routes    │        │
│  │workspace CRUD│ │file CRUD     │ │staging/tools/gen│        │
│  └──────┬───────┘ └──────┬───────┘ └────────┬─────────┘        │
│         └────────────────┼─────────────────┘                  │
│                   http_routes.py (合并层)                       │
│                   ws_routes.py (WebSocket)                      │
│                   schemas.py / services.py / common.py          │
│                   common.py: ProcessManager (v6.5.0)           │
├───────────────────────────────────────────────────────────────┤
│  Core Kernel (file_cortex_core/)                               │
│  ┌─────────┐ ┌──────────┐ ┌─────────┐ ┌────────────────┐      │
│  │ config  │ │ security │ │ search  │ │ context        │      │
│  │DataMgr  │ │PathValid │ │Strategy │ │ OOM保护 v6.5.0 │      │
│  └─────────┘ └──────────┘ └─────────┘ └────────────────┘      │
│  ┌─────────┐ ┌──────────┐ ┌─────────┐ ┌────────────────┐      │
│  │ file_io │ │ actions  │ │ format  │ │ duplicate      │      │
│  │walk_filt│ │FileOps   │ │FormatU  │ │ SHA256 worker  │      │
│  │         │ │DI v6.3.2 │ │         │ │ daemon v6.5.0  │      │
│  └─────────┘ └──────────┘ └─────────┘ └────────────────┘      │
│  ┌──────────────────┐ ┌────────────────────────────┐           │
│  │ process_utils    │ │ fctx.py CLI v6.5.0         │           │
│  │terminate/cleanup │ │ search + export commands   │           │
│  └──────────────────┘ └────────────────────────────┘           │
└───────────────────────────────────────────────────────────────┘
```

### 1.2 核心设计原则

| 原则 | 实现 | 位置 |
|------|------|------|
| **单源真理 (SSOT)** | `DataManager` Pydantic 模型驱动，所有配置经由此处 | `config.py` |
| **路径归一化** | `PathValidator.norm_path()` 确保跨平台 key 唯一性 | `security.py` |
| **防御深度** | HTTP + WebSocket 双通道 Token 认证 | `web_app.py`, `ws_routes.py` |
| **遍历共享** | `FileUtils.walk_filtered()` 统一所有目录遍历 | `file_io.py` |
| **原子写入** | 配置保存使用 tempfile + os.replace + Windows 锁重试 | `config.py` |
| **策略解耦** | `PathMatcher` / `ContentMatcher` 匹配逻辑与遍历分离 | `search.py` |
| **进程终止统一** | `process_utils.py` 统一跨平台进程终止 (Windows/POSIX) | `process_utils.py` |
| **OOM 保护** | 上下文导出限流 500文件/50MB，防止大项目内存溢出 | `context.py` (v6.5.0) |
| **进程容器** | `ProcessManager` 线程安全、50 容量限制 | `common.py` (v6.5.0) |

---

## 2. 参数动态对齐机制

### 2.1 问题背景

v6.3.1 审计发现大量前后端参数不一致的 BUG — 前端发送 `token_threshold: 100000` 但后端默认为 `128000`，导致静默丢弃。根本原因：参数定义分散在多个文件中，缺乏统一的校验管道。

v6.5.0 进一步移除了所有硬编码默认值，测试文件中的 `== 128000` 改用 `GlobalSettings().token_threshold` 动态获取。

### 2.2 对齐清单

以下关键参数必须在前后端保持一致。每次代码变更后，运行 `pytest` 会自动验证这些参数。

| # | 参数 | 前端位置 | 后端模型 | API 传输 |
|---|------|----------|----------|----------|
| 1 | `token_threshold` | `state.js` (128000) | `GlobalSettings.token_threshold` | `POST /api/global/settings` |
| 2 | `token_ratio` | `state.js` (4.0) | `GlobalSettings.token_ratio` | `POST /api/global/settings` |
| 3 | `preview_limit_mb` | `main.js` (1.0) | `GlobalSettings.preview_limit_mb` | `POST /api/global/settings` |
| 4 | `allowed_extensions` | `main.js` ("") | `GlobalSettings.allowed_extensions` | `POST /api/global/settings` |
| 5 | `api_token` | `window.__FCTX_API_TOKEN__` | `os.getenv("FCTX_API_TOKEN")` | HTTP `X-API-Token` + WS `token` |
| 6 | `__version__` | `index.html` `{{ version }}` | `__init__.py` | Jinja2 注入 |
| 7 | `max_search_size_mb` | `state.js` (10) | `ProjectConfig.max_search_size_mb` | `POST /api/project/settings` |
| 8 | `wsSearch` | `state.js:config.endpoints.wsSearch` | `ws_routes.py` `/ws/search` | WebSocket URL |
| 9 | `wsExecute` | `state.js:config.endpoints.wsExecute` | `ws_routes.py` `/ws/execute` | WebSocket URL |

### 2.3 添加新参数的规范流程

添加新参数时，必须按以下顺序更新 **6 处**：

```
1. file_cortex_core/config.py        ← Pydantic 模型字段定义
2. routers/schemas.py                ← Request Schema (前端→API)
3. static/js/state.js                ← 前端 defaults / config.endpoints
4. templates/index.html              ← 模板变量注入（如需要）
5. routers/ (对应 route 文件)         ← API 处理逻辑
6. tests/                            ← 新增参数传递链路测试
```

### 2.4 校验测试

| 测试函数 | 文件 | 验证内容 |
|----------|------|----------|
| `test_global_settings_roundtrip` | `test_bugfix_v632.py` | token_threshold + preview_limit_mb 双向传递 |
| `test_global_settings_handles_allowed_extensions` | `test_comprehensive_v63.py` | allowed_extensions 字段 |
| `test_api_token_header_forward` | `test_comprehensive_v63.py` | API Token HTTP 认证 |
| `test_api_index_page_injects_version` | `test_comprehensive_v63.py` | 版本号模板注入 |
| `test_ws_search_endpoint` | `test_web_endpoints.py` | WebSocket wsSearch 端点 |
| `test_ws_execute_endpoint` | `test_web_endpoints.py` | WebSocket wsExecute 端点 |

---

## 3. v6.5.0 重构深度解析

### 3.1 Google Python Style Guide 全面审计

v6.5.0 对整个代码库（28 个源文件, 6,441 行）进行了完整的 Google Python Style Guide 规范审计，涵盖 7 个维度：

| 维度 | 检查标准 | 发现 | 修复 |
|------|----------|------|------|
| **命名规范** | 类名 CapWords/函数 snake_case/常量 UPPER_CASE/遮蔽内置 | 1 处 | `format`→`fmt` in `mcp_server.py` |
| **Import 规范** | 3层分组/字母序/绝对引用/无通配符 | 5 文件 | 分组+顺序修正 |
| **类型注解** | 公共函数完整参数+返回值注解 | 8 处 | `-> None`, `Generator[...]`, `Callable[...]` |
| **异常处理** | 日志含栈轨迹/无 bare except/raise 正确 | 23 处 | `logger.exception()` |
| **__main__ 规范** | 只调用 `main()`，不内联代码 | 2 处 | `file_search.py` + `build_exe.py` |
| **线程安全** | daemon 属性构造器传参 | 2 类 | `SearchWorker` + `DuplicateWorker` |
| **代码格式** | 行长 100/尾随空格/空白 | 26 处 | JS 文件尾随空格清理 |

**核心修改**:

```python
# ❌ 旧: 异常日志丢失栈轨迹
logger.error(f"Failed to save configuration: {e}")

# ✅ 新: logger.exception 自动捕获栈轨迹
logger.exception("Failed to save configuration")

# ❌ 旧: __main__ 内联代码
if __name__ == "__main__":
    root = tk.Tk()
    app = FileCortexApp(root)
    root.mainloop()

# ✅ 新: main() 函数封装
def main() -> None:
    root = tk.Tk()
    app = FileCortexApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
```

### 3.2 上下文导出 OOM 保护 (v6.5.0)

大规模项目（万级文件）导出上下文时可能耗尽内存。v6.5.0 在 `ContextFormatter` 中增加了两层保护：

```python
# file_cortex_core/context.py
MAX_EXPORT_FILES: Final = 500          # 单次导出的硬上限
MAX_TOTAL_CONTENT_BYTES: Final = 50 * 1024 * 1024  # 50 MB

# 第一层: 文件数量截断
if len(all_files) > max_files:
    all_files = all_files[:max_files]

# 第二层: 内容大小截断
for ...:
    total_bytes += len(content.encode("utf-8", errors="replace"))
    if total_bytes >= MAX_TOTAL_CONTENT_BYTES:
        # 截断标记插入
        break
```

可用参数 `max_files` 同时暴露给 `to_xml()` 和 `to_markdown()` 方法，调用方可根据场景调整。

### 3.3 ProcessManager 封装 (v6.5.0)

`routers/common.py` 中的 `ProcessManager` 类对之前杂乱的 `ACTIVE_PROCESSES` 全局字典进行了封装：

```python
class ProcessManager:
    """Thread-safe container for tracking active subprocesses."""

    def __init__(self, max_processes: int = 50):
        self._processes: dict[int, subprocess.Popen] = {}
        self._lock = threading.Lock()
        self._max = max_processes

    def register(self, pid: int, proc: subprocess.Popen) -> bool:
        with self._lock:
            if len(self._processes) >= self._max:
                return False
            self._processes[pid] = proc
            return True

    def unregister(self, pid: int) -> None: ...
    def get(self, pid: int) -> subprocess.Popen | None: ...
    def clear(self) -> None: ...
    @property
    def pids(self) -> list[int]: ...   # 返回快照副本
    @property
    def active_count(self) -> int: ...

# 旧 API 别名保持向后兼容
ACTIVE_PROCESSES: Final = process_manager._processes  # 只读引用
PROCESS_LOCK: Final = process_manager._lock            # 只读引用
```

### 3.4 CLI 搜索与导出 (v6.5.0)

`fctx.py` 新增两个子命令：

```bash
# 搜索文件
python fctx.py search <project_path> <query> \
    --mode smart|exact|regex|content \
    --exclude "*.log" \
    --case-sensitive \
    --inverse \
    --max-results 100

# 导出上下文
python fctx.py export <project_path> \
    --format markdown|xml \
    --output context.md \
    --max-files 200
```

### 3.5 线程安全改进 (v6.5.0)

`SearchWorker` 和 `DuplicateWorker` 继承自 `threading.Thread`，以前使用已弃用的 `self.daemon = True` 属性赋值。v6.5.0 改为构造器参数传递：

```python
# ❌ 旧 (属性赋值)
super().__init__()
self.daemon = True

# ✅ 新 (构造器参数, Python 3.9+ 推荐)
super().__init__(daemon=True)
```

---

## 4. 常见 BUG 模式与预防

### 4.1 参数不一致

**模式**: 前/后端默认值不同，设置被静默丢弃。

**根因**: 参数定义分散，缺少单一校验源。

**预防**:
- 所有参数必须在 `GlobalSettings` / `ProjectConfig` Pydantic 模型中有单一默认值
- 测试文件中的默认值校验应使用 `GlobalSettings()` 动态获取而非硬编码数字
- 新增参数必须同步更新「参数对齐清单」并添加测试

### 4.2 NoneType 崩溃

**模式**: `self.current_proj_config["groups"]` 当 `current_proj_config` 为 None 时崩溃。

**根因**: 方法在项目未加载时被调用（如 UI 初始化渲染）。

**预防**:
- 依赖项目数据的方法首行添加 `if not self.current_proj_config: return`
- 在 `__init__` 中将可变属性显式初始化为安全默认值

### 4.3 分支逻辑错误

**模式**: `if/else` 链中最后一个 `else` 覆盖了前面的 `if` 分支。

**根因**: 使用 `if/if/else` 而非 `if/elif/else`。

**预防**:
- 使用 `if/elif/else` 互斥链
- 在最后用 `if not args.command:` 独立检查无命令状态

### 4.4 弃用 API 使用

**模式**: 新代码使用 `dm.data["projects"]`（dict API）而非 `dm.config.projects`（Pydantic model）。

**预防**:
- `dm.data[...]` 只应出现在 `DataManager` 自身实现中
- 外部代码一律使用 `dm.config.xxx` 模型属性

### 4.5 异常日志丢失栈轨迹

**模式**: `logger.error(f"Failed: {e}")` 只记录了异常信息，丢失栈轨迹。

**预防**:
- 在 except 块中统一使用 `logger.exception("...")`（自动包含异常名称、消息、栈轨迹）
- 如需 `logger.warning`，添加 `exc_info=True` 参数

### 4.6 WebSocket 消息解析

**模式**: `JSON.parse(event.data)` 无异常保护，恶意/损坏数据导致静默断开。

**预防**:
- 所有 `onmessage` 中 `JSON.parse()` 必须包装在 try/catch 中
- 解析失败应记录日志并跳过该消息（而非断开连接）

---

## 5. 测试架构

### 5.1 测试分层

```
tests/                              597 项测试 (v6.5.0)
├── test_v8_comprehensive.py        77 tests  ← v6.5.0 新增 (DI/OOM/CLI/ProcessManager)
├── test_coverage_fill.py           20 tests  ← v6.5.0 新增 (process_utils/ProcessManager)
├── test_frontend_contract.py       31 tests  ← v6.5.0 新增 8 项前端契约
├── test_bugfix_v7.py               85 tests  ← v6.4.0 BUG修复/前端/WebSocket 回归
├── test_bugfix_v633.py             24 tests  ← v6.3.3 BUG修复 + 边界覆盖
├── test_bugfix_v632.py             54 tests  ← v6.3.2 BUG修复 + 边界覆盖
├── test_comprehensive_v63.py       73 tests  ← v6.3.1 CLI/MCP/Web/安全/前端契约
├── test_comprehensive.py           52 tests  ← 核心功能 + 高级边界
├── test_search_engine.py           20 tests  ← 搜索引擎矩阵 (4 mode × 2 params)
├── test_security_resilience.py     23 tests  ← 路径验证器全矩阵 (15 场景)
├── test_fileops_advanced.py         9 tests  ← 文件操作完整覆盖
├── test_dm_config.py                7 tests  ← DataManager 持久化/并发/弃用API迁移
├── test_web_api_advanced.py        21 tests  ← 创建/归档/重命名/设置/Token
├── test_web_endpoints.py           12 tests  ← 端点契约 (含 WS wsSearch/wsExecute)
├── test_core_integration.py        11 tests  ← 集成测试
├── test_context_formatter.py        6 tests  ← XML/MD 导出
├── test_mcp_server.py               3 tests  ← MCP 协议
├── test_utils_format.py             8 tests  ← 格式化/Token估算
├── test_scenarios.py                2 tests  ← 端到端场景
├── test_ai_enhanced.py              7 tests  ← AI 上下文/Blueprint
├── test_api_v6.py                  12 tests  ← API 版本演进
├── test_additional_coverage.py     30 tests  ← 边缘覆盖
│
└── conftest.py                              ← 共享 fixture + DataManager.reset()
```

### 5.2 测试隔离

所有测试共享统一的隔离策略：

```python
@pytest.fixture(autouse=True)
def _reset_singleton():
    """每个测试前后调用 DataManager.reset() 确保单例隔离"""
    DataManager.reset()
    FileUtils.clear_cache()
    yield
    # ... 清理活跃进程 + DataManager.reset()
```

### 5.3 关键 Fixture

| Fixture | 用途 |
|---------|------|
| `mock_project` | 创建含 10+ 种文件类型的临时项目 |
| `noisy_project` | GBK 编码 + minified JS + 正常文件 |
| `stress_project` | 100+ 文件的多目录项目 |
| `clean_config` | 隔离的 DataManager（patch config 路径） |
| `api_client` | FastAPI TestClient（隔离 config） |
| `project_client` | 已注册项目的 api_client |
| `mock_popen` | 模拟 subprocess.Popen 用于 ActionBridge 测试 |

---

## 6. DataManager 依赖注入

### 6.1 使用场景

```python
from file_cortex_core import DataManager

# 1. 单例访问（向后兼容，生产环境）
dm = DataManager()

# 2. 创建独立实例（测试隔离）
dm = DataManager.create()

# 3. 上下文管理器（临时替换全局单例）
with DataManager.activate(custom_dm):
    service.do_work()  # 内部调用 DataManager() 获得 custom_dm

# 4. 重置（测试 teardown）
DataManager.reset()
```

### 6.2 最佳实践

- **路由层**: 使用 `Depends(get_dm)` 作为 FastAPI 依赖
- **核心模块**: 接受 `dm: DataManager | None = None` 参数，默认为 `DataManager()`
- **测试**: `clean_config` fixture 自动提供隔离实例

---

## 7. walk_filtered 遍历

`FileUtils.walk_filtered()` 统一了项目中所有 `os.walk` 调用：

```python
for full_path, rel_path in FileUtils.walk_filtered(
    root, excludes, git_spec,
    include_dirs=False,
    stop_event=cancel_event,
):
    # full_path: pathlib.Path 绝对路径
    # rel_path: pathlib.Path 相对路径（相对于 root）
```

调用点: `search_generator()`, `get_project_items()`, `DuplicateWorker.run()`

---

## 8. 版本历史

| 版本 | 日期 | 关键变更 |
|------|------|----------|
| **6.5.0** | **2026-05-29** | **Google Style 全审计, 23 处日志规范化, 8 类型注解, CLI search/export, OOM 保护, ProcessManager, 前端 8 项修复, 597 tests** |
| **6.4.0** | **2026-05-24** | **process_utils提取, 14类型标注, 3处XSS修复, api.js集中化, 前端可折叠面板, SRI哈希, tag管理, file创建, actionModal, 479 tests** |
| 6.3.3 | 2026-05-16 | 8 BUG修复, Google Style整肃, 24新测试, 372 tests |
| 6.3.2 | 2026-05-14 | 8 BUG修复, DataManager DI, 路由拆分, walk_filtered, 348 tests |
| 6.3.1 | 2026-05-10 | 全量审计, 10 BUG修复, 前后端一致性, 294 tests |
| 6.3.0 | 2026-04-22 | 内核解耦, WebSocket Auth, Blueprint XML |

---

## 9. 完整工作原理

### 9.1 请求生命周期 (Web API)

```
浏览器请求
    ↓
FastAPI Middleware (web_app.py:verify_api_token)
    ├── Token 校验: X-API-Token header → os.getenv("FCTX_API_TOKEN")
    ├── CORS 校验: Origin → _is_wildcard_origin(ALLOWED_ORIGINS)
    └── 放行或 401/403
    ↓
路由层 (routers/)
    ├── project_routes.py → 工作区注册/配置/收藏
    ├── fs_routes.py → 文件 CRUD/预览/归档
    └── action_routes.py → 暂存/导出/工具/设置
    ↓
服务层 (routers/services.py)
    ├── get_dm() → DataManager 单例
    ├── is_path_safe() → PathValidator 沙盒
    └── get_valid_project_root() → 项目根解析
    ↓
内核层 (file_cortex_core/)
    ├── DataManager: Pydantic V2 强类型配置, 原子 os.replace 持久化
    ├── FileUtils: walk_filtered 统一遍历, read_text_smart 编码探测
    ├── SearchWorker: 策略化匹配引擎 (daemon=True)
    ├── ContextFormatter: LLM 上下文 XML/Markdown 导出 (OOM 保护)
    ├── ActionBridge: 外部工具执行桥接 (DI 支持)
    └── process_utils: 跨平台进程终止 (Windows/POSIX)
```

### 9.2 搜索引擎管线

```
用户输入 (query string)
    ↓
SearchQuery (Pydantic model) → 参数校验与归一化
    ↓
PathMatcher 初始化
    ├── 解析 positive/negative tags
    ├── 编译 regex patterns (以 / 包裹)
    └── 分词 keywords → plain_pos + regex_pos
    ↓
walk_filtered() 生成器 → yield (full_path, rel_path)
    ├── os.walk + dirs[:] 剪枝
    ├── should_ignore() 过滤
    │   ├── manual_excludes (fnmatch)
    │   └── git_spec (pathspec.PathSpec)
    └── stop_event 检查 (取消支持)
    ↓
匹配判断 (4模式):
    smart: all plain keywords in path AND all regex match AND no neg keywords
    exact: query substring in path (case-sensitive optional)
    regex: compiled regex.search(path)
    content: ThreadPoolExecutor 并发读取 + ContentMatcher.match_file
    ↓
结果队列 → UI 批次渲染 (100条/tick)
```

### 9.3 安全沙盒机制

```
PathValidator.is_safe(target, root)
    ↓
平台检测 (ntpath.splitdrive / UNC 前缀)
    ├── Windows: ntpath.normpath → lower → 前缀比较
    │   └── UNC 拦截: "\\\\" 或 "//" 开头 → False
    └── POSIX: os.path.abspath → 前缀比较
    ↓
PathValidator.norm_path(p)
    ├── os.path.abspath → / 替换
    ├── Windows: lower() + 长路径前缀 "\\\\?\\" 移除
    └── 尾部 / 移除 (除非驱动器根)
    ↓
PathValidator.validate_project(path)
    ├── UNC 拦截
    ├── 存在性 + 目录检查
    ├── 敏感目录拦截 (.git, .env, __pycache__, node_modules...)
    └── 系统目录拦截 (Windows SYSTEMROOT, POSIX /etc /usr...)
```

### 9.4 上下文生成管线

```
用户选择文件路径列表
    ↓
ContextFormatter.to_xml(paths, root_dir, ...)
    ↓
flatten_paths() → 展开目录 → 过滤 → 去重
    ↓
blueprint (可选) → FileUtils.generate_ascii_tree(max_depth=5)
    ↓
OOM 保护:
    ├── 文件数量 > MAX_EXPORT_FILES (500) → 截断
    └── 累计内容 > MAX_TOTAL_CONTENT_BYTES (50MB) → 截断
    ↓
逐文件处理:
    ├── is_binary() → 跳过
    ├── read_text_smart() → charset_normalizer 编码探测 + lru_cache
    ├── NoiseReducer.clean() → 超长行/Base64块 去噪 (可选)
    ├── CDATA 转义: "]]>" → "]]]]><![CDATA[>"
    └── 格式化: <file path="..." size="...KB">...</file>
    ↓
XML 输出: <instruction> + <blueprint> + <context> + 文件列表 + </context>
```

### 9.5 进程终止管线

```
工具执行超时 / WebSocket 断开 / 测试清理
    ↓
process_utils.terminate_process(proc, timeout=3.0)
    ↓
平台检测:
    ├── Windows: subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)])
    │   └── /T → 终止整个进程树
    └── POSIX: proc.terminate() (SIGTERM)
        ├── proc.wait(timeout) → 成功
        └── TimeoutExpired → proc.kill() (SIGKILL)
    ↓
返回 bool (True=成功终止, False=超时/失败)
    ↓
cleanup_processes(process_list) → 批量清理, 记录日志
```

调用点:
- `action_routes.py` → `terminate_process(process)`
- `ws_routes.py` → `terminate_process(proc)`
- `common.py` → `cleanup_processes(staging_processes)` on shutdown

### 9.6 参数动态对齐机制

前后端关键参数通过统一校验管道保持一致：

```
参数定义 (单一来源):
  Pydantic Model (GlobalSettings / ProjectConfig)
      ↓
  model_dump() → 前端 defaults (state.js)
      ↓
  /api/global/settings → 动态获取后端默认值
      ↓
  HTTP Request → Pydantic Model → model_validate()
      ↓
  model_dump_json() → os.replace() 原子持久化
```

### 9.7 数据持久化原子性

```
DataManager.save()
    ↓
config.model_dump_json(indent=4)
    ↓
tempfile.NamedTemporaryFile (同目录)
    ↓
f.write(data_json)
    ↓
os.replace(temp, config) ← 原子替换 (Windows: MAX_SAVE_RETRIES 次重试 + sleep)
    ↓
异常清理: os.unlink(temp)
```

### 9.8 关键编码探测 (二级缓存)

```
read_text_smart(file_path, max_bytes)
    ↓
stat: (mtime, size) → 缓存 key
    ↓
charset_normalizer.from_bytes(header[:65536])
    ↓
decode(encoding, errors="ignore")
    ↓
fallback: decode("utf-8", errors="ignore") → 返回空字符串兜底
```

---

## 10. 前端安全架构

### 10.1 API 请求集中化

```
前端 API 调用 (12处 fetch → 2个辅助方法)
    ↓
api._post(url, data)
    ├── URLSearchParams 表单编码 → 统一 Content-Type
    └── fetch() → resp.json()
    ↓
api._postJson(url, json)
    ├── JSON.stringify() 序列化 → 统一 Content-Type: application/json
    └── fetch() → resp.json()
```

所有端点 URL 来自 `state.js:config.endpoints` 单一来源。

### 10.2 XSS 防御数据流

```
用户输入 (搜索框/标签名/文件名)
    ↓
后端返回 (JSON 或 HTML 片段)
    ↓
前端渲染:
    ├── Markdown 内容 → marked.parse(content, { sanitize: true })
    ├── HTML 文本 → escapeHtml(str) → 创建 textNode 再读 innerHTML
    ├── DOM 属性 → textContent 赋值 (非 innerHTML)
    └── CDN 资源 → SRI integrity 哈希校验
    ↓
浏览器渲染 (安全)
```

### 10.3 WebSocket 健壮性

```
WebSocket onmessage
    ↓
try:
    data = JSON.parse(event.data)
    ↓
    消息路由 (search_result / execute_output / error)
    ↓
    UI 更新
except (SyntaxError, TypeError):
    console.error("Invalid WS message", event.data)
    // 跳过该消息，不中断连接
```

### 10.4 stageAll BUG 修复 (v6.5.0)

**问题**: `stageAll` 按钮发送搜索模式字符串 (`"smart"`) 给后端 staging API，但后端期望固定模式 `"files"`。

**修复**: 前端 `stageAll` 方法直接发送 `mode="files"` 而非 `state.searchMode`。

**影响范围**: 仅 Web 前端 `main.js` 中的 `stageAll` handler。

---
