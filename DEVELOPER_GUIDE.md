# FileCortex - 开发者指南 (DEVELOPER_GUIDE)

欢迎参与 FileCortex 的开发。本项目采用核心逻辑 (`core_logic.py`) + 多端适配 (`file_search.py`, `web_app.py`, `fctx.py`) 的分层架构。

## 🏗️ 核心架构

### 1. 权限与安全校验
为了防止路径越权 (Path Traversal) 和 命令注入 (Command Injection)，本项目采用了严格的校验机制：
*   **路径权限注册制**: 只有通过 `/api/open` 显式注册的目录才能作为 `project_root`。
*   **黑名单保护**: `PathValidator` 采用路径组件精准匹配，拦截对 `Windows`, `System32`, `.git`, `.env`, `.ssh` 等系统及敏感目录的访问。
*   **ActionBridge 安全执行 (v5.1+)**: 
    *   **Windows**: 采用 `shell=True` 以兼容复杂的 CMD 模板，但对所有上下文变量（如 `{path}`, `{name}`）进行 `win_quote` (双引号包裹) 强制转义，彻底杜绝注入。
    *   **Unix/macOS**: 采用 `shell=False` 结合 `shlex.split` 进行列表级参数分发，符合 POSIX 安全标准。
*   **操作审计**: 关键 API 操作（如删除、ARCHIVE、SAVE）必须在 `web_app.py` 中记录带有 `AUDIT` 前缀的日志。

### 2. 参数一致性与动态对齐 (Consistency & Self-healing)
保持跨端参数一致性是核心设计点，旨在消除“配置漂移”：
*   **SSOT (Single Source of Truth)**: `DataManager` 采用 **线程安全的原子单例模式 (Atomic Singleton)**。配置加载 (`load_initial`) 在 `__new__` 的锁保护下仅执行一次，确保多线程并发下的数据一致性。
*   **Schema 自动演进 (Schema Evolution)**: `DataManager.get_project_data` 在加载 JSON 时，会递归检测并补全缺失字段。v5.1 新增了 `tool_rules` 字段，支持基于文件模式的智能工具推荐。
*   **无状态 API**: Web 端接口严禁依赖后台全局变量。所有文件操作必须显式传递 `project_path`，以支持多标签页并发。

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
