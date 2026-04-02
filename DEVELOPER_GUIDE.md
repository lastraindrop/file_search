# FileCortex - 开发者指南 (DEVELOPER_GUIDE)

欢迎参与 FileCortex 的开发。本项目采用核心业务包 (`file_cortex_core/`) + 多端视角 (`file_search.py`, `web_app.py`, `fctx.py`) 的解耦架构。

## 🏗️ 核心架构

### 1. 权限与安全校验
为了防止路径越权 (Path Traversal) 和 命令注入 (Command Injection)，本项目采用了严格的校验机制：
*   **路径权限注册制**: 只有通过 `/api/open` 显式注册的目录才能作为 `project_root`。
*   **黑名单保护**: `PathValidator` 采用路径组件精准匹配，拦截对 `Windows`, `System32`, `.git`, `.env` 等系统及敏感目录的访问。
*   **ActionBridge 安全执行 (v5.3+)**: 
    *   **Windows**: 默认对不含 Shell 元字符 (`&|<>^%`) 的模板采用 `shell=False` 列表模式执行，彻底杜绝注入。若模板包含元字符，则回退至 `shell=True` 并强制执行 `win_quote` 转义审计。
    *   **Unix/macOS**: 采用 `shell=False` 结合 `shlex.split` 进行列表级参数分发，符合 POSIX 安全标准。
*   **API 权限隔离 (v5.1)**: 所有项目相关 API (Config, Settings, Session, Favorites) 必须强制过 `get_valid_project_root` 校验，防止越权访问。
*   **Settings API 白名单 (v5.3)**: `DataManager.MUTABLE_SETTINGS` 定义了允许通过 `/api/project/settings` 修改的字段。敏感字段（如 `groups`, `notes`, `tags`）被保护在白名单外。
*   **专用配置 API (v5.3)**: `custom_tools` 与 `quick_categories` 已移至专用端点 (`/api/project/tools`, `/api/project/categories`)，并增加了格式校验与路径穿越防护，彻底切断了通过 settings 注入实现 RCE 的可能性。
*   **跨项目移动防护 (v5.3)**: `/api/fs/move` 路由强制执行 `src_root == dst_root` 校验，禁止在不同项目间移动文件。
*   **资源泄漏防御 (v5.3)**: 全局强制使用 `with os.scandir(...)` 以确保文件句柄及时关闭，解决 Windows 下的文件占用问题。
*   **操作审计**: 关键 API 操作（如删除、ARCHIVE、SAVE）必须在 `web_app.py` 中记录带有 `AUDIT` 前缀的日志。

### 2. 微内核设计与包结构 (Micro-kernel & Package Structure)
# FileCortex v5.7.1 - 工业级大规模文件分析与 Kontext 搜集工具
FileCortex v5.2 将逻辑从单文件 `core_logic.py` 迁移至 `file_cortex_core/` 包，实现了高内聚低耦合：
*   **config.py**: 线程安全的 `DataManager` 单例，管理全局配置与项目 Schema。
*   **security.py**: `PathValidator` 负责所有路径的安全性校验。
*   **utils.py**: 提供文件 IO 工具、语言识别及最新的 **Token 估算** 与 **Prompt 模板渲染** 逻辑。
*   **actions.py**: 封装物理文件操作 (`FileOps`) 与外部工具执行桥接 (`ActionBridge`)。
*   **search.py**: 负责高性能的多线程并发文件检索。

### 3. AI 上下文增强 (AI Context Orchestration)
*   **Token 计数**: 采用 `FormatUtils.estimate_tokens` 进行快速预判，帮助用户在发送给 LLM 前评估成本。
*   **Prompt 预设**: `DataManager` 内置了 `prompt_templates` 字段，允许用户预设“代码审查”、“生成单测”等常用指令，并一键组装上下文。

### 4. 数据一致性与参数对齐 (Dynamic Alignment)
为了确保多端（Web, Desktop, CLI）及不同版本间的稳定性，本项目遵循以下核心原则：
*   **Schema 自愈 (Self-Healing)**: `DataManager._apply_default_schema` 是核心稳定性来源。任何配置读取均会自动合并 `DEFAULT_SCHEMA`，确保即使用户手动修改了配置文件或使用了旧版配置，系统也能自动补全缺失字段（如 `search_settings`），防止运行时 `KeyError`。
*   **路径归一化确定性标准 (Deterministic Normalization - v5.7)**: 为了彻底消除 Windows 路径漂移，项目强制要求所有外部路径（TreeView 选择、API 参数等）通过 `PathValidator.norm_path` 处理。该方法改用 `os.path.abspath` 以绕过 `pathlib` 随 CWD 变动的特性，并强制执行 **小写化 + POSIX 斜杠** 转换，确保内存缓存键的唯一性。
*   **状态同步隔离原则 (Memory Reference Isolation - v5.7)**: 为了防止 UI 列表与后台 `DataManager` 共享内存引用，规定在 UI 刷新或清单修改时必须使用 `list()` 或 `.copy()`。这杜绝了 UI `clear()` 操作误伤持久化配置的问题。
*   **参数动态对齐协议 (Parameter Alignment Protocol - v5.7)**: 
    - **API 上下文保障**: 任何涉及文件列表统计（如 `StatsRequest`）或内容生成（如 `GenerateRequest`）的模型必须显式包含 `project_path`。这是为了在调用 `FileUtils.flatten_paths` 时能够动态定位 `.gitignore` 过滤器，确保前端统计与后端处理的过滤逻辑达到 100% 同步。
    - **OOM 拦截规约**: 所有的文本读取操作必须调用 `FileUtils.read_text_smart`。该方法限制了编码采样的最大字节数，并在读取前进行二进制检测，防止因读取 GB 级日志而发生 OOM 崩溃。
    - **UI 回调防御 (Audit Fix - v5.7.1)**: 为了防止 Tkinter 回调中的 `AttributeError` 导致界面静默失效，所有 UI 渲染回调（如 `_update_stats_ui`）必须包含 `try...except` 保护，且依赖的工具类方法必须由核心库 `FormatUtils` 统一维护，严禁在 UI 层自行拼接复杂的数值格式。

### 5. 并发控制与资源生命周期 (Concurrency & Lifecycle - v5.7.1)
*   **单例原子锁 (Atomic Singleton Lock)**: `DataManager` 在 `__new__` 阶段实现了双重检查锁定，且所有写操作均由 `self._lock` (RLock) 保护，严禁在高并发循环中直接读写私有成员。
*   **资源强制回收原则**: 所有的搜索生成器 (`search_generator`) 必须在 `finally` 块中对挂起的 `content_futures` 执行 `f.cancel()`，确保在生成器关闭或异常退出时，线程池任务能够被立即回收。
*   **Unix 进程树清理机制**:
    - **隔离执行**: 外部工具必须通过 `ActionBridge.create_process` 启动，且非 Windows 环境下强制启用 `start_new_session=True` 以启用进程组治理。
    - **分级终止**: 优先使用 `os.killpg(os.getpgid(pid), signal.SIGTERM)` 杀掉整个进程组，仅在失败时回退至单 PID 或单信号模式。
*   **Web 路由线程策略**:
    - **同步 `def` 路由**: 适用于所有 I/O 密集型操作（如文件读取、重命名、归档）。FastAPI 会在独立线程池中执行这些路由，避免阻塞主事件循环。
    - **异步 `async def` 路由**: 仅适用于纯 CPU 逻辑、单纯的数据库查询或 Websocket 握手，严禁在其中执行阻塞式 `os` 或 `pathlib` 调用。
*   **原子写入策略**: 使用 `.tmp` 临时文件 + `os.replace` 确保文件写入的完整性。

### 6. 防错检查清单 (Post-Audit Anti-Patterns)
在开发新功能时，必须避开以下 v5.3 审计发现的常见陷阱：
*   **[禁止] 重复定义 API 模型**: 严禁在同一文件（如 `web_app.py`）中定义两个相同名称的 `BaseModel` 类，这会导致 FastAPI 路由解析失败。
*   **[禁止] 相对导入根目录脚本**: `web_app.py` 等根目录脚本不应使用 `from .xxx`，应直接使用 `from xxx`。
*   **[强制] 路由唯一性**: 发布前必须验证是否存在同名的 API 装饰器（如 `@app.post("/settings")` 定义了两次），FastAPI 会优先执行最后一个，导致前端调用 422。
*   **[强制] 跨平台 Open 实现**: 严禁直接调用 `os.startfile`，必须通过封装好的 `FileUtils.open_path_in_os` 进行分发。

### 7. 文件操作与快速分类 (FileOps & Quick Categorization)
... (后续章节递增)
*   **文件操作**: 实现了安全的文件移动、删除和归档功能。
*   **快速分类**: `batch_categorize` 模块允许基于规则对文件进行批量排序和分类。

### 8. 动作桥接 (ActionBridge)
*   **模板引擎**: ActionBridge 是一个模板引擎，用于在暂存文件上执行外部命令行工具 (CLI)。
*   **上下文注入**: 支持将文件路径、项目根目录、文件扩展名等上下文信息注入到 CLI 命令中，实现高度灵活的自动化操作。

### 9. UI 层 (UI Layer)
*   **解耦设计**: Tkinter 和 FastAPI 接口是解耦的，允许独立开发和部署。

## 🧪 测试方法论
本项目包含 124 个自动化测试，覆盖了从核心逻辑到 Web 接口的全路径。
*   **动态参数对齐 (Dynamic Parameter Alignment)**: 
    *   **原则**: 所有跨端 (UI/Web/CLI) 调用的路径解析必须经过 `PathValidator.norm_path` 处理。
    *   **原则**: 所有的命令执行必须通过 `ActionBridge._prepare_execution` 枢纽，严禁在业务逻辑中直接拼凑 shell 命令。
    *   **测试要求**: 新增的功能必须在 Windows 和 Unix 逻辑路径上分别通过 `test_audit_fixes.py` 类型的覆盖率验证。
*   **测试隔离与自修复 (v5.3)**: `conftest.py` 引入了 `autouse` fixture，在每个测试运行前后强制重置 `DataManager` 单例和缓存，彻底消除测试间的交叉污染。
*   **测试隔离规范**: **严禁在单项测试中重写 `TestClient` 或 `DataManager` 实例。** 所有的测试必须共享 `conftest.py` 提供的隔离配置文件 `api_test_config.json`，以防止泄露至用户的真实配置目录。
*   **参数矩阵覆盖 (Matrix Testing)**: 在 `test_search.py` 中覆盖了搜索模式、正反向、大小写、排除规则的组合。
*   **零硬编码 (Zero Hardcoding)**: 测试 Fixture 严禁出现绝对路径。使用 `system_dir` 等动态感知 Fixture，确保测试在任何环境下皆能“动态对齐”。
*   **端到端工作流 (E2E)**: `test_e2e.py` 模拟了从“打开项目 -> 搜索并暂存 -> 选择模板 -> 生成上下文”的完整 AI 辅助心流。
*   **Mock 边界**: 使用 `pytest` 对 PowerShell 或 subprocess 调用进行隔离 Mock，确保逻辑验证不依赖于特定宿主环境的权限。
*   **状态隔离专项测试 (v5.7)**: [test_ui_state_isolation.py](tests/test_ui_state_isolation.py) 专门验证 UI 操作与后台配置的内存解耦。
*   **递归与去重测试 (v5.7)**: [test_recursive_collection.py](tests/test_recursive_collection.py) 验证复杂目录结构下的上下文输出唯一性。
*   **测试运行**: 
    ```bash
    python -m pytest
    ```
    v5.7 版本共包含 **107** 项全自动化测试用例，涵盖安全、并发与同步加固。

## 🛠️ 打包与分发
*   **桌面版**: 使用 `build_exe.py` (封装了 PyInstaller) 进行单文件打包。
*   **网页版**: 基于 FastAPI，由于前端依赖 CDN (Bootstrap/Highlight.js)，部署时需确保网络连通性或将其本地化。

## 📝 贡献准则
1.  **KISS 原则**: 优先通过内置库解决问题，减少不必要的第三方依赖。
2.  **防御性编程**: 对所有涉及 `root` 以外的 IO 操作直接进行 `is_safe` 熔断处理。
