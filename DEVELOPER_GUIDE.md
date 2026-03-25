# FileCortex - 开发者指南 (DEVELOPER_GUIDE)

欢迎参与 FileCortex 的开发。本项目采用核心逻辑 (`core_logic.py`) + 多端适配 (`file_search.py`, `web_app.py`, `fctx.py`) 的分层架构。

## 🏗️ 核心架构

### 1. 权限与安全校验
为了防止路径越权 (Path Traversal) 和 XSS 攻击，本项目采用了严格的校验机制：
*   **路径权限注册制**: 只有通过 `/api/open` 显式注册的目录才能作为 `project_root`。
*   **黑名单保护**: `PathValidator` 采用路径组件精准匹配，拦截对 `Windows`, `System32`, `etc` 等系统关键目录的直接访问。
*   **文件名隔离**: 在重命名和归档操作中，严格限制文件名不得包含路径分隔符。
*   **XSS 防护**: Web 前端在渲染任何用户可控的文件名/路径时，必须通过 `App.escapeHtml` 进行转义，禁止直接使用 `.innerHTML` 拼接。
*   **规范**: 禁止使用 `os.path.join` 处理未经过滤的用户输入路径，一律使用 `pathlib` 结合 `is_safe` 方法。
*   **操作审计**: 关键 API 操作（如删除、ARCHIVE、SAVE）必须在 `web_app.py` 中记录带有 `AUDIT` 前缀的日志，注明发起路径与目标动作。

### 2. 参数一致性与动态对齐 (Consistency & Self-healing)
保持跨端 (Tkinter/Web) 参数一致性是核心设计点，旨在消除“配置漂移”：
*   **SSOT (Single Source of Truth)**: 所有的路径权限、排除规则 (`excludes`) 及 工作区设置 (`staging_list`) 统一由 `DataManager` 管理。UI 层（无论是 React/JS 还是 Tkinter）在变更设置后必须第一时间调用 `DataManager.save()`，确保重启后的“状态复原”。
*   **动态参数链路**: 以 `MAX_RESULTS` 为例：
    1.  **定义**: 在 `DataManager.DEFAULT_SCHEMA` 中定义默认值。
    2.  **分发**: 搜索请求发起时，API/GUI 层从 `proj_config` 提取值，并将其透传至 `SearchWorker` 或 `search_generator`。
    3.  **熔断**: `core_logic.py` 内置多级 `break` 机制，确保即使在并发多线程生成器模式下，总结果数也不会突破此阈值，防御内存溢出。
*   **Schema 自动对齐 (Schema Evolution)**: 这是一个关键的韧性设计。`DataManager.get_project_data` 在加载 JSON 时，会递归检测并补全所有缺失的 v5.0+ 字段（如 `quick_categories`, `custom_tools`）。这保证了旧版本用户在升级到 v5.0 时，配置不会报错且能立即获得新功能。
*   **无状态 API (Statelessness)**: Web 端接口严禁依赖后台全局变量。所有文件操作必须显式传递 `project_path`，以支持多标签页并发。
*   **数据原子性**: 采用 `os.replace` 确保配置在写入瞬间的完整性，防止断电或崩溃导致 JSON 文件损坏。

### 3. 并发安全与数据一致性 (Concurrency Safety)
*   **线程锁**: `DataManager` 内置了 `threading.Lock()`，所有的 `load` 和 `save` 操作均处于线程安全上下文中，防止多端或高频 API 请求引发的竞态条件。
*   **原子写入**: 配置保存采用**原子重命名策略** (写入 `.json.tmp` 后调用 `os.replace` 覆盖)。这确保了即使在极端情况 (如进程意外中断) 下，配置文件也不会被截断或损坏。
*   **跨平台 IO 分发**: 避免直接使用如 `os.startfile` 等强依赖系统的 API。所有的原生系统调用均已抽象入 `FileUtils.open_path_in_os`，依据 `sys.platform` 进行动态分发。

### 4. 文件操作与快速分类 (FileOps & Quick Categorization)
*   **文件操作**: 实现了安全的文件移动、删除和归档功能。
*   **快速分类**: `batch_categorize` 模块允许基于规则对文件进行批量排序和分类。

### 5. 动作桥接 (ActionBridge)
*   **模板引擎**: ActionBridge 是一个模板引擎，用于在暂存文件上执行外部命令行工具 (CLI)。
*   **上下文注入**: 支持将文件路径、项目根目录、文件扩展名等上下文信息注入到 CLI 命令中，实现高度灵活的自动化操作。

### 6. UI 层 (UI Layer)
*   **解耦设计**: Tkinter 和 FastAPI 接口是解耦的，允许独立开发和部署。

## 🧪 测试方法论
本项目坚持 **100% 关键路径覆盖** 且遵循 **“零硬编码”原则**。
*   **零硬编码 (Zero Hardcoding)**: 测试 fixture 严禁直接定义驱动器号或系统绝对路径（如 `C:/Windows`）。应使用 `system_dir` 等动态感知 fixture，确保测试在任何环境下皆可即插即用，杜绝 False Negative。
*   **Mock 边界**: 使用 `pytest` 对 PowerShell 或 subprocess 调用进行隔离 Mock，确保逻辑验证不依赖于特定宿主环境的权限。
*   **并发压力测试**: 对核心引擎（如自适应检索、配置读写锁）进行 Stress Testing 覆盖。
*   **测试运行**: 
    ```bash
    python -m pytest
    ```

## 🛠️ 打包与分发
*   **桌面版**: 使用 `build_exe.py` (封装了 PyInstaller) 进行单文件打包。
*   **网页版**: 基于 FastAPI，由于前端依赖 CDN (Bootstrap/Highlight.js)，部署时需确保网络连通性或将其本地化。

## 📝 贡献准则
1.  **KISS 原则**: 优先通过内置库解决问题，减少不必要的第三方依赖。
2.  **防御性编程**: 对所有涉及 `root` 以外的 IO 操作直接进行 `is_safe` 熔断处理。
