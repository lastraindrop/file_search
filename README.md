# FileCortex v6.5.0 (工作区编排助手)

> **版本**: 6.5.0 | **日期**: 2026-06-07 | **测试**: 629 passed | **代码质量**: Ruff 0 errors | **Google Style**: 全规范审计完成

## 核心理念
- **Orchestration over Collection**: 从简单的"收集"进化为对工作区的"编排"。
- **Engineering Excellence**: 基于 **Pydantic V2** 与 **Google Python Style Guide** 构建的健壮内核。

## 主要功能

### 微内核架构
- **强类型配置**: Pydantic 模型驱动的 `DataManager`，实现配置的自愈与严谨校验。
- **策略化搜索**: 多维度匹配策略 (smart/exact/regex/content)，易于扩展。
- **安全沙盒**: `PathValidator` 路径权限注册制，UNC 拦截，敏感目录保护。

### 现代化交互
- **控制中心**: Web 端顶部全局过滤器工具栏，统一配置排除规则与搜索模式。
- **智能查重**: DuplicateFinder 支持"保留最早/最晚"一键筛选冗余文件。
- **XML 导出引擎**: 支持 CDATA 封装，提升 LLM 对复杂代码片段的解析精度。
- **项目蓝图**: 一键生成项目架构 ASCII 快照。

### 性能与安全
- **二级探测缓存**: `(path, mtime, size)` 编码探测缓存，大幅提升大规模文件读取速度。
- **安全沙盒增强**: 符号链接遍历防护 (`Path.resolve()`)、统一入口验证 (`PathValidator.validate_project()`)
- **内存防溢出**: 并发内容搜索 `max_bytes` 物理隔离 + 导出 OOM 保护 (500文件/50MB上限)。
- **Token 预算预警**: UI 超阈值颜色警示。
- **API Token 认证**: HTTP Header + WebSocket 双通道验证。

### 多端访问
- **桌面版 (Tkinter)**: 原生桌面体验，目录树导航与实时预览。
- **网页版 (FastAPI)**: ES6 模块化前端，WebSocket 实时搜索流，自定义右键菜单。
- **CLI 工具 (fctx.py)**: Headless 环境命令行编排 (search/export 子命令)。
- **MCP Server**: Model Context Protocol 服务器，AI Agent 原生调用。

### 文件管理
- **多模式搜索**: smart/exact/regex/content 四种模式，positive/negative 标签。
- **批量操作**: 批量重命名、批量删除、批量归档 (ZIP)。
- **查重工具**: 大小预筛 + SHA256 策略。
- **快速分类**: 自定义类别目录移动。

### 前端增强
- **标签管理 (Tag Management)**: 前端 UI 支持添加/移除标签。
- **文件创建 (File Creation)**: 文件创建模态框，支持从 UI 直接创建新文件。
- **可折叠面板 (Collapsible Left Panel)**: 左面板从 Bootstrap 标签页重构为可折叠区域，提升操作效率。
- **SRI 哈希 (Subresource Integrity)**: 所有 CDN 资源添加 SRI 哈希；marked@12.0.0 和 mermaid@10.9.0 版本锁定。

---

## 详细文档
- [综合审计与执行计划](COMPREHENSIVE_ANALYSIS_V8.md)
- [技术指南 (架构/参数对齐/防BUG)](TECHNICAL_GUIDE.md)
- [开发者指南](DEVELOPER_GUIDE.md)
- [项目路线图](ROADMAP.md)
- [测试说明](tests/README.md)

---

## 快速开始

### 环境要求
- Python 3.10+
- Windows/macOS/Linux

### 安装
```bash
pip install -r requirements.txt
```

### 桌面版
```bash
python file_search.py
```

### 网页版
```bash
python web_app.py
# 浏览器访问 http://127.0.0.1:8000
```

### CLI 工具
```bash
python fctx.py open .
python fctx.py projects
python fctx.py stage <project> <file>
python fctx.py search <project> <query> --mode smart
python fctx.py export <project> --format markdown --output context.md
```

### MCP Server
```bash
python mcp_server.py --transport stdio
```

---

## 测试

### 运行所有测试
```bash
python -m pytest
```

### 测试覆盖
- **629 项核心测试**: 涵盖内核逻辑、安全沙盒、API 契约、搜索矩阵、WebSocket 实时流、前端模块化契约、CLI、MCP、Windows 兼容性、进程管理、OOM 保护。
- **测试结果**: 629 passed, 0 failed
- **代码质量**: Ruff 0 errors, Google Style 全审计项通过

### 代码质量检查
```bash
python -m ruff check .
python -m ruff check . --fix
python -m pytest
```

---

## 项目结构

```
file_cortex_core/          # 微内核逻辑包
├── __init__.py           # 统一接口 + 版本声明
├── config.py            # DataManager (SSOT 配置中心)
├── security.py         # PathValidator (安全沙盒与归一化)
├── file_io.py          # FileUtils (物理 I/O 与 Gitignore)
├── format_utils.py     # FormatUtils (格式化与 Token 估算)
├── context.py          # ContextFormatter (AI 上下文导出, OOM 保护)
├── search.py           # SearchWorker (搜索引擎, ThreadPoolExecutor)
├── actions.py          # FileOps, ActionBridge (执行桥接, DI 支持)
├── duplicate.py        # DuplicateWorker (SHA256 查重)
├── process_utils.py    # 跨平台进程终止工具
└── gui/                # GUI 组件 (BatchRename, DuplicateFinder)

routers/                  # FastAPI 路由层
├── http_routes.py      # 合并层 (向后兼容)
├── project_routes.py   # 工作区/项目管理
├── fs_routes.py        # 文件系统 CRUD
├── action_routes.py    # 暂存/工具/上下文/设置
├── ws_routes.py        # WebSocket 搜索/工具流
├── services.py         # 业务逻辑服务层
├── schemas.py          # Pydantic 参数校验模型
└── common.py           # ProcessManager (线程安全进程管理)

static/js/                # ES6 模块化前端
├── main.js             # 流程控制 + debounced syncStagingToBackend
├── state.js            # 状态中心 + config.endpoints 集中管理
├── api.js              # API 封装 (_post / _postJson 集中化)
└── ui.js               # UI 渲染驱动

file_search.py           # Tkinter 桌面版 (入口 main())
web_app.py              # FastAPI Web 入口
fctx.py                # CLI 工具入口
mcp_server.py          # MCP 协议服务
build_exe.py            # PyInstaller 打包脚本 (入口 main())
```

---

## 参数动态对齐

前后端关键参数已统一校验，确保一致性：

| 参数 | 前端 | 后端 | 默认 |
|------|------|------|------|
| `token_threshold` | `state.js` | `GlobalSettings` | 128000 |
| `token_ratio` | `state.js` | `GlobalSettings` | 4.0 |
| `preview_limit_mb` | settings modal | `GlobalSettings` | 1.0 |
| `allowed_extensions` | settings modal | `GlobalSettings` | "" |
| `api_token` | `window.__FCTX_API_TOKEN__` | env `FCTX_API_TOKEN` | - |
| `wsSearch` | `state.js:config.endpoints` | ws_routes.py `/ws/search` | - |
| `wsExecute` | `state.js:config.endpoints` | ws_routes.py `/ws/execute` | - |
| `__version__` | `index.html` `{{ version }}` | `__init__.py` | 6.5.0 |

---

## 环境变量
| 变量 | 说明 | 默认值 |
|-----|------|-------|
| FCTX_API_TOKEN | API 认证 Token | (无) |
| FCTX_ALLOWED_ORIGINS | 允许的跨域来源 | * |
| FCTX_PORT | Web 服务端口 | 8000 |
| FCTX_PROD | 生产模式 (隐藏错误详情) | (无) |
| FCTX_EXEC_TIMEOUT | 工具执行超时(秒) | 300 |

---

## 许可证
MIT License
