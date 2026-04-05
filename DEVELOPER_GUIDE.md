# FileCortex - 开发者指南 (DEVELOPER_GUIDE)

欢迎参与 FileCortex 的开发。本项目采用核心业务包 (`file_cortex_core/`) + 多端视角 (`file_search.py`, `web_app.py`, `fctx.py`) 的解耦架构。

## 🏗️ 核心架构

### 1. 权限与安全校验
为了防止路径越权 (Path Traversal) 和 命令注入 (Command Injection)，本项目采用了严格的校验机制：
*   **路径权限注册制**: 只有通过 `/api/open` 显式注册的目录才能作为 `project_root`。
*   **黑名单保护**: `PathValidator` 采用路径组件精准匹配，拦截对 `Windows`, `System32`, `.git`, `.env` 等系统及敏感目录的访问。
*   **ActionBridge 安全执行 (v5.8.1)**: 
    *   **Windows**: 默认对不含 Shell 元字符 (`&|<>^%`) 的模板采用 `shell=False` 列表模式。**v5.8.1 引入了智能内置命令识别**：系统会自动检测第一个单词（如 `echo`, `dir`），并先剥离其可能的引号，再调用 `shutil.which`。若未找见可执行文件，则标记为内置命令并 fallback 到 `shell=True`。
    *   **注入防御 (v5.8.1)**：在启用 `shell=True` 时，ActionBridge 会自动将参数中的 `%` 符号转义为 `%%`。这确保了用户文件名中的特殊字符会被原文传递至外部工具，而不会被 CMD 环境变量扩展。
    *   **Unix/macOS**: 采用 `shell=False` 结合 `shlex.split` 进行列表级参数分发。
*   **API 前端通信 (App._fetch)**: 前端 `app.js` 现已强制要求所有异步请求通过 `App._fetch` 枢纽，实现自动的 4xx/5xx 状态码拦截、JSON 响应解构及全局加载状态一致性。
*   **API 权限隔离 (v5.1)**: 所有项目相关 API (Config, Settings, Session, Favorites) 必须强制过 `get_valid_project_root` 校验，防止越权访问。
*   **Settings API 白名单 (v5.3)**: `DataManager.MUTABLE_SETTINGS` 定义了允许通过 `/api/project/settings` 修改的字段。敏感字段（如 `groups`, `notes`, `tags`）被保护在白名单外。
*   **专用配置 API (v5.3)**: `custom_tools` 与 `quick_categories` 已移至专用端点 (`/api/project/tools`, `/api/project/categories`)，并增加了格式校验与路径穿越防护，彻底切断了通过 settings 注入实现 RCE 的可能性。
*   **跨项目移动防护 (v5.3)**: `/api/fs/move` 路由强制执行 `src_root == dst_root` 校验，禁止在不同项目间移动文件。
*   **资源泄漏防御 (v5.8)**: 全局强制使用 `with os.scandir(...)`。针对 Windows 平台，在测试清理阶段引入了 **Active Process Termination** 机制，通过 `taskkill /F /T` 强力释放被残留子进程锁定的目录。
*   **操作审计**: 关键 API 操作（如删除、ARCHIVE、SAVE）必须在 `web_app.py` 中记录带有 `AUDIT` 前缀的日志。

### 2. 微内核设计与包结构 (Micro-kernel & Package Structure)
# FileCortex v5.8 - 工业级大规模文件分析与 Kontext 搜集工具
FileCortex v5.2 将逻辑从单文件 `core_logic.py` 迁移至 `file_cortex_core/` 包，实现了高内聚低耦合：
*   **config.py**: 线程安全的 `DataManager` 单例。**v5.8 强化了原子锁机制**，确保“读取-修改-保存”全生命周期由 `RLock` 保护，杜绝并发下的字典大小变动错误。
*   **security.py**: `PathValidator` 负责所有路径的安全性校验。
*   **utils.py**: 提供文件 IO 工具、语言识别、Token 估算及 **路径搜集符号自定义** 逻辑。
*   **actions.py**: 封装物理文件操作 (`FileOps`) 与外部工具执行桥接 (`ActionBridge`)。
*   **search.py**: 负责高性能的多线程并发文件检索。

### 3. AI 上下文增强 (AI Context Orchestration)
*   **Token 计数**: 采用 `FormatUtils.estimate_tokens` 进行快速预判。**v5.8 增加了 Token 预算警告**，UI 会在超过阈值时通过颜色警示用户。
*   **Prompt 预设**: `DataManager` 内置了 `prompt_templates` 和 `collection_profiles` (搜集预设)，允许用户快速配置导出符号（如 `@`, `/`）。

### 4. 数据一致性与参数对齐 (Dynamic Alignment)
为了确保多端（Web, Desktop, CLI）及不同版本间的稳定性，本项目遵循以下核心原则：
*   **Schema 自愈 (Self-Healing)**: `DataManager._apply_default_schema` 是核心稳定性来源。任何配置读取均会自动合并 `DEFAULT_SCHEMA`，确保即使用户手动修改了配置文件或使用了旧版配置，系统也能自动补全缺失字段（如 `search_settings`, `collection_profiles`），防止运行时 `KeyError`。
*   **路径归一化确定性标准 (Deterministic Normalization - v5.7)**: 为了彻底消除 Windows 路径漂移，项目强制要求所有外部路径（TreeView 选择、API 参数等）通过 `PathValidator.norm_path` 处理。该方法改用 `os.path.abspath` 以绕过 `pathlib` 随 CWD 变动的特性，并强制执行 **小写化 + POSIX 斜杠** 转换，确保内存缓存键的唯一性。
*   **状态同步隔离原则 (Memory Reference Isolation - v5.7)**: 为了防止 UI 列表与后台 `DataManager` 共享内存引用，规定在 UI 刷新或清单修改时必须使用 `list()` 或 `.copy()`。这杜绝了 UI `clear()` 操作误伤持久化配置的问题。
*   **参数动态对齐协议 (Parameter Alignment Protocol - v5.8)**: 
    - **API 上下文保障**: 任何涉及文件列表统计（如 `StatsRequest`）或内容生成（如 `GenerateRequest`）的模型必须显式包含 `project_path`。
    - **UI 过滤器同步**: 桌面端清单过滤器 (`staging_filter`) 与后端统计逻辑通过动态对齐协议实现 100% 同步，确保“所见即所得”的统计体验。
    - **OOM 拦截规约**: 所有的文本读取操作必须调用 `FileUtils.read_text_smart`。该方法限制了编码采样的最大字节数，并在读取前进行二进制检测，防止因读取 GB 级日志而发生 OOM 崩溃。
    - **UI 回调防御 (Audit Fix - v5.7.1)**: 为了防止 Tkinter 回调中的 `AttributeError` 导致界面静默失效，所有 UI 渲染回调（如 `_update_stats_ui`）必须包含 `try...except` 保护。

### 5. 并发控制与资源生命周期 (Concurrency & Lifecycle - v5.8)
*   **双重原子锁**: `DataManager` 在 `__new__` 阶段实现了双重检查锁定，且所有写操作均由 `self._lock` (RLock) 保护。**v5.8 修正了方法级锁定缺失**，确保了在多线程 Web 环境下的配置完整性。
*   **资源强制回收原则**: 所有的搜索生成器 (`search_generator`) 必须在 `finally` 块中执行 `gen.close()`，确保在生成器关闭或异常退出时，线程池任务能够被立即回收。
*   **跨平台进程树清理**:
    - **Windows**: 使用 `taskkill /F /T` 确保子进程及关联句柄被物理释放。
    - **Unix**: 优先使用 `os.killpg(os.getpgid(pid), signal.SIGTERM)` 杀掉整个进程组。
*   **Web 路由线程策略**:
    - **同步 `def` 路由**: 适用于所有 I/O 密集型操作。FastAPI 会在独立线程池中执行这些路由，避免阻塞主事件循环。
    - **原子写入策略 (v5.7.1 Hardening)**: 关键配置写入强制采用 `tempfile.NamedTemporaryFile(delete=False)` 模式。这确保了在 Windows 下文件句柄能够在移动 (`os.replace`) 前被物理关闭。
    - **强制超时暗杀 (Executive Assassination)**: 所有外部工具执行均内置 300s 强制超时。

### 6. 防错检查清单 (Post-Audit Anti-Patterns)
在开发新功能时，必须避开以下常见陷阱：
*   **[禁止] 重复定义 API 模型**: 严禁在同一文件（如 `web_app.py`）中定义两个相同名称的 `BaseModel` 类。
*   **[禁止] 相对导入根目录脚本**: `web_app.py` 等根目录脚本不应使用 `from .xxx`，应直接使用 `from xxx`。
*   **[强制] 路由唯一性**: 发布前必须验证是否存在同名的 API 装饰器。
*   **[强制] 跨平台 Open 实现**: 严禁直接调用 `os.startfile`，必须通过封装好的 `FileUtils.open_path_in_os` 进行分发。

### 7. 文件操作与快速分类 (FileOps & Quick Categorization)
*   **批量过滤**: 实现了清单内容的实时正则/字符串过滤，支持一键移除过滤项。
*   **文件操作**: 实现了安全的文件移动、删除和归档功能。

### 8. 动作桥接 (ActionBridge)
*   **模板引擎**: ActionBridge 是一个模板引擎，用于在暂存文件上执行外部命令行工具 (CLI)。
*   **上下文注入**: 支持将文件路径、项目根目录、文件扩展名等上下文信息注入到 CLI 命令中。

### 9. UI 层 (UI Layer)
*   **解耦设计**: Tkinter 和 FastAPI 接口是解耦的。
*   **非侵入式反馈**: 桌面端全面引入 **Status Stream** 机制，取代了大部分阻塞式的 Messagebox。
*   **内容检索**: 预览区支持 `Ctrl+F` 实时检索。

## 🧪 测试方法论
本项目包含 177 个自动化测试，覆盖了从核心逻辑到 Web 接口的全路径。
*   **动态参数对齐 (Dynamic Parameter Alignment)**: 
    *   **原则**: 所有跨端 (UI/Web/CLI) 调用的路径解析必须经过 `PathValidator.norm_path` 处理。
    *   **原则**: 所有的命令执行必须通过 `ActionBridge._prepare_execution` 枢纽，严禁在业务逻辑中直接拼凑 shell 命令。
*   **测试隔离与自修复 (v5.8)**: `conftest.py` 引入了 **Active Cleanup**。在每个测试运行后，会自动杀掉所有注册在 `ACTIVE_PROCESSES` 中的进程，确保 Windows 目录句柄被释放。
*   **项目本地沙箱化**: 为了解决 Windows `PermissionError`，测试临时目录统一迁移至 `.pytest_tmp/` 并加入 `.gitignore`。
*   **测试运行**: 
    ```bash
    python -m pytest
    ```
    v5.8 版本共包含 **177** 项全自动化测试用例。

## 🛠️ 打包与分发
*   **桌面版**: 使用 `build_exe.py` (封装了 PyInstaller) 进行单文件打包。
*   **网页版**: 基于 FastAPI。

## 📝 贡献准则
1.  **KISS 原则**: 优先通过内置库解决问题，减少不必要的第三方依赖。
2.  **防御性编程**: 对所有涉及 `root` 以外的 IO 操作直接进行 `is_safe` 熔断处理。
