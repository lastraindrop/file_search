# FileCortex 技术指南 — 架构、参数对齐与测试策略

> **版本**: 6.3.3 | **测试**: 372 passed | **ruff**: 0 errors

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
│  │tkinter  │ │ REST + WS     │ │argparse│ │ FastMCP       │    │
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
├───────────────────────────────────────────────────────────────┤
│  Core Kernel (file_cortex_core/)                               │
│  ┌─────────┐ ┌──────────┐ ┌─────────┐ ┌────────────────┐      │
│  │ config  │ │ security │ │ search  │ │ context        │      │
│  │DataMgr  │ │PathValid │ │Strategy │ │ LLM formatting │      │
│  └─────────┘ └──────────┘ └─────────┘ └────────────────┘      │
│  ┌─────────┐ ┌──────────┐ ┌─────────┐ ┌────────────────┐      │
│  │ file_io │ │ actions  │ │ format  │ │ duplicate      │      │
│  │walk_filt│ │FileOps   │ │FormatU  │ │ SHA256 worker  │      │
│  └─────────┘ └──────────┘ └─────────┘ └────────────────┘      │
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

---

## 2. 参数动态对齐机制

### 2.1 问题背景

v6.3.1 审计发现大量前后端参数不一致的 BUG — 前端发送 `token_threshold: 100000` 但后端默认为 `128000`，导致静默丢弃。根本原因：参数定义分散在多个文件中，缺乏统一的校验管道。

### 2.2 对齐清单

以下 8 个关键参数必须在前后端保持一致。每次代码变更后，运行 `pytest` 会自动验证这些参数。

| # | 参数 | 前端位置 | 后端模型 | API 传输 |
|---|------|----------|----------|----------|
| 1 | `token_threshold` | `state.js:20` (128000) | `GlobalSettings.token_threshold` | `POST /api/global/settings` |
| 2 | `token_ratio` | `state.js:21` (4.0) | `GlobalSettings.token_ratio` | `POST /api/global/settings` |
| 3 | `preview_limit_mb` | `main.js:260` (1.0) | `GlobalSettings.preview_limit_mb` | `POST /api/global/settings` |
| 4 | `allowed_extensions` | `main.js:263` ("") | `GlobalSettings.allowed_extensions` | `POST /api/global/settings` |
| 5 | `api_token` | `index.html:430` → `window.__FCTX_API_TOKEN__` | `os.getenv("FCTX_API_TOKEN")` | HTTP `X-API-Token` + WS `token` |
| 6 | `apply_noise_reducer` | `schemas.py:30` | `GenerateRequest.apply_noise_reducer` | `POST /api/generate` |
| 7 | `__version__` | `index.html` `{{ version }}` | `__init__.py:3` | Jinja2 注入 |
| 8 | `max_search_size_mb` | `state.js` (10) | `ProjectConfig.max_search_size_mb` | `POST /api/project/settings` |

### 2.3 添加新参数的规范流程

添加新参数时，必须按以下顺序更新 **5 处**：

```
1. file_cortex_core/config.py        ← Pydantic 模型字段定义
2. routers/schemas.py                ← Request Schema (前端→API)
3. static/js/state.js                ← 前端 defaults / 读取逻辑
4. templates/index.html              ← 模板变量注入（如需要）
5. routers/http_routes.py / fs_routes.py / action_routes.py  ← API 处理逻辑
6. tests/                            ← 新增参数传递链路测试
```

### 2.4 校验测试

| 测试函数 | 文件 | 验证内容 |
|----------|------|----------|
| `test_global_settings_roundtrip` | `test_bugfix_v632.py:445` | token_threshold + preview_limit_mb 双向传递 |
| `test_global_settings_handles_allowed_extensions` | `test_comprehensive_v63.py` | allowed_extensions 字段 |
| `test_api_generate_with_noise_reducer` | `test_comprehensive_v63.py` | noise_reducer 参数链路 |
| `test_api_token_header_forward` | `test_comprehensive_v63.py` | API Token HTTP 认证 |
| `test_api_index_page_injects_version` | `test_comprehensive_v63.py` | 版本号模板注入 |

---

## 3. 常见 BUG 模式与预防

### 3.1 参数不一致

**模式**: 前/后端默认值不同，设置被静默丢弃。

**根因**: 参数定义分散，缺少单一校验源。

**预防**:
- 所有参数必须在 `GlobalSettings` / `ProjectConfig` Pydantic 模型中有单一默认值
- 前端通过 `/api/global/settings` 动态获取后端默认值，而非硬编码
- 新增参数必须同步更新「参数对齐清单」并添加测试

### 3.2 NoneType 崩溃

**模式**: `self.current_proj_config["groups"]` 当 `current_proj_config` 为 None 时崩溃。

**根因**: 方法在项目未加载时被调用（如 UI 初始化渲染）。

**预防**:
- 依赖项目数据的方法首行添加 `if not self.current_proj_config: return`
- 在 `__init__` 中将可变属性显式初始化为安全默认值（如 `self.results_count = 0`）

### 3.3 分支逻辑错误

**模式**: `if/else` 链中最后一个 `else` 覆盖了前面的 `if` 分支。

**根因**: `if cmd == "a" ... if cmd == "b" ... else: help()` — 所有未识别命令（包括 `"a"` 通过后）都会落入 `else`。

**预防**:
- 使用 `if/elif/else` 互斥链
- 在最后用 `if not args.command:` 独立检查无命令状态

### 3.4 弃用 API 使用

**模式**: 新代码使用 `dm.data["projects"]`（dict API）而非 `dm.config.projects`（Pydantic model）。

**根因**: 开发者复制旧代码。

**预防**:
- `DEVELOPER_GUIDE.md` 明确标注 `.data` 为 DEPRECATED
- Code review 检查：`dm.data[` 只应出现在 `DataManager` 自身实现中

### 3.5 可选导入污染

**模式**: `__init__.py` 无条件 `from .gui import *` 导致 headless 环境 (Web/CLI/MCP) 被迫依赖 tkinter。

**预防**: 使用 `try/except ImportError` 包装 GUI 导入，headless 环境下设为 None。

---

## 4. 测试架构

### 4.1 测试分层

```
tests/                              372 项测试
├── test_bugfix_v633.py             24 tests  ← v6.3.3 BUG修复 + 边界覆盖
├── test_bugfix_v632.py             54 tests  ← v6.3.2 BUG修复 + 边界覆盖
├── test_comprehensive_v63.py       73 tests  ← v6.3.1 CLI/MCP/Web/安全
├── test_additional_coverage.py     30 tests  ← 边缘覆盖
├── test_comprehensive.py           52 tests  ← 核心功能 + 高级边界
│
├── test_search_engine.py           20 tests  ← 搜索引擎矩阵 (4 mode × 2 params)
├── test_security_resilience.py     23 tests  ← 路径验证器全矩阵 (15 场景)
├── test_fileops_advanced.py         9 tests  ← 文件操作完整覆盖
├── test_dm_config.py                7 tests  ← DataManager 持久化/并发
├── test_web_api_advanced.py        21 tests  ← 创建/归档/重命名/设置/Token
├── test_web_endpoints.py            9 tests  ← 端点契约
├── test_core_integration.py        11 tests  ← 集成测试
├── test_context_formatter.py        6 tests  ← XML/MD 导出
├── test_mcp_server.py               3 tests  ← MCP 协议
├── test_utils_format.py             8 tests  ← 格式化/Token估算
├── test_scenarios.py                2 tests  ← 端到端场景
├── test_ai_enhanced.py              7 tests  ← AI 上下文/Blueprint
├── test_api_v6.py                  12 tests  ← API 版本演进
├── test_frontend_contract.py        7 tests  ← 前端结构契约
│
└── conftest.py                              ← 共享 fixture + DataManager.reset()
```

### 4.2 测试隔离

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

### 4.3 关键 Fixture

| Fixture | 用途 |
|---------|------|
| `mock_project` | 创建含 10+ 种文件类型的临时项目 |
| `noisy_project` | GBK 编码 + minified JS + 正常文件 |
| `stress_project` | 100+ 文件的多目录项目 |
| `clean_config` | 隔离的 DataManager（patch config 路径） |
| `api_client` | FastAPI TestClient（隔离 config） |
| `project_client` | 已注册项目的 api_client |

---

## 5. DataManager 依赖注入

### 5.1 使用场景

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

### 5.2 最佳实践

- **路由层**: 使用 `Depends(get_dm)` 作为 FastAPI 依赖
- **核心模块**: 接受 `dm: DataManager | None = None` 参数，默认为 `DataManager()`
- **测试**: `clean_config` fixture 自动提供隔离实例

---

## 6. walk_filtered 遍历

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

## 7. 版本历史

| 版本 | 日期 | 关键变更 |
|------|------|----------|
| 6.3.3 | 2026-05-16 | 8 BUG修复, Google Style整肃, 24新测试, 文档完善, 372 tests |
| 6.3.2 | 2026-05-14 | 8 BUG修复, DataManager DI, 路由拆分, walk_filtered, 348 tests |
| 6.3.1 | 2026-05-10 | 全量审计, 10 BUG修复, 前后端一致性, 294 tests |
| 6.3.0 | 2026-04-22 | 内核解耦, WebSocket Auth, Blueprint XML |

---

## 8. 完整工作原理

### 8.1 请求生命周期 (Web API)

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
    ├── SearchWorker: 策略化匹配引擎
    ├── ContextFormatter: LLM 上下文 XML/Markdown 导出
    └── ActionBridge: 外部工具执行桥接
```

### 8.2 搜索引擎管线

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

### 8.3 安全沙盒机制

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

### 8.4 上下文生成管线

```
用户选择文件路径列表
    ↓
ContextFormatter.to_xml(paths, root_dir, ...)
    ↓
flatten_paths() → 展开目录 → 过滤 → 去重
    ↓
blueprint (可选) → FileUtils.generate_ascii_tree(max_depth=5)
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

### 8.5 参数动态对齐机制

前后端 8 个关键参数通过统一校验管道保持一致：

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

### 8.6 数据持久化原子性

```
DataManager.save()
    ↓
config.model_dump_json(indent=4)
    ↓
tempfile.NamedTemporaryFile (同目录)
    ↓
f.write(data_json)
    ↓
os.replace(temp, config) ← 原子替换 (Windows: 5次重试 + sleep)
    ↓
异常清理: os.unlink(temp)
```

### 8.7 关键编码探测 (二级缓存)

```
read_text_smart(file_path, max_bytes)
    ↓
stat: (mtime, size) → 缓存 key
    ↓
charset_normalizer.from_bytes(header[:65536])
    ↓
decode(encoding, errors="ignore")
    ↓
fallback: decode("utf-8", errors="ignore")
```

> 所有关键路径均通过单元测试覆盖。新增参数必须同步更新 5 处 (Pydantic 模型/前端 defaults/Schema/API route/测试)。
