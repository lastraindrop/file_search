# FileCortex - 开发者指南 (DEVELOPER_GUIDE)

欢迎参与 FileCortex 的开发。本项目采用核心业务包 (`file_cortex_core/`) + 多端视角 (`file_search.py`, `web_app.py`, `fctx.py`) 的解耦架构。

## 🏗️ 核心架构

### 1. 权限与安全校验
为了防止路径越权 (Path Traversal) 和 命令注入 (Command Injection)，本项目采用了严格的校验机制：
*   **路径权限注册制**: 只有通过 `/api/open` 显式注册的目录才能作为 `project_root`。
*   **黑名单保护**: `PathValidator` 采用路径组件精准匹配，拦截对 `Windows`, `System32`, `.git`, `.env`, `.ssh` 等系统及敏感目录的访问。
*   **ActionBridge 安全执行 (v5.1+)**: 
    *   **Windows**: 采用 `shell=True` 以兼容复杂的 CMD 模板，但对所有上下文变量（如 `{path}`, `{name}`）进行 `win_quote` (双引号包裹) 强制转义，彻底杜绝注入。
    *   **Unix/macOS**: 采用 `shell=False` 结合 `shlex.split` 进行列表级参数分发，符合 POSIX 安全标准。
*   **API 权限隔离 (v5.1)**: 所有项目相关 API (Config, Settings, Session, Favorites) 必须强制过 `get_valid_project_root` 校验，防止越权访问。
*   **Settings API 白名单 (v5.3)**: `DataManager.MUTABLE_SETTINGS` 定义了允许通过 `/api/project/settings` 修改的字段。敏感字段（如 `groups`, `notes`, `tags`）被保护在白名单外。
*   **专用配置 API (v5.3)**: `custom_tools` 与 `quick_categories` 已移至专用端点 (`/api/project/tools`, `/api/project/categories`)，并增加了格式校验与路径穿越防护，彻底切断了通过 settings 注入实现 RCE 的可能性。
*   **跨项目移动防护 (v5.3)**: `/api/fs/move` 路由强制执行 `src_root == dst_root` 校验，禁止在不同项目间移动文件。
*   **资源泄漏防御 (v5.3)**: 全局强制使用 `with os.scandir(...)` 以确保文件句柄及时关闭，解决 Windows 下的文件占用问题。
*   **操作审计**: 关键 API 操作（如删除、ARCHIVE、SAVE）必须在 `web_app.py` 中记录带有 `AUDIT` 前缀的日志。

### 2. 微内核设计与包结构 (Micro-kernel & Package Structure)
FileCortex v5.2 将逻辑从单文件 `core_logic.py` 迁移至 `file_cortex_core/` 包，实现了高内聚低耦合：
*   **config.py**: 线程安全的 `DataManager` 单例，管理全局配置与项目 Schema。
*   **security.py**: `PathValidator` 负责所有路径的安全性校验。
*   **utils.py**: 提供文件 IO 工具、语言识别及最新的 **Token 估算** 与 **Prompt 模板渲染** 逻辑。
*   **actions.py**: 封装物理文件操作 (`FileOps`) 与外部工具执行桥接 (`ActionBridge`)。
*   **search.py**: 负责高性能的多线程并发文件检索。

### 3. AI 上下文增强 (AI Context Orchestration)
*   **Token 计数**: 采用 `FormatUtils.estimate_tokens` 进行快速预判，帮助用户在发送给 LLM 前评估成本。
*   **Prompt 预设**: `DataManager` 内置了 `prompt_templates` 字段，允许用户预设“代码审查”、“生成单测”等常用指令，并一键组装上下文。

### 4. 参数一致性与动态对齐 (Parameter Consistency & Dynamic Alignment)
为了确保多端（Web, Desktop, CLI）及不同版本间的稳定性，本项目遵循以下核心原则：
*   **Schema 自愈 (Self-Healing)**: `DataManager.DEFAULT_SCHEMA` 是全局配置的单一事实来源。任何配置读取均会自动合并默认值，确保旧版配置文件在升级后能自动补全缺失字段（如 `prompt_templates`）。
*   **动态路径感知**: 严禁在核心逻辑中硬编码特定的路径分隔符 (`/` 或 `\`)。所有的路径比较与安全校验均应通过 `pathlib.Path.resolve()` 后的组件进行，以实现跨系统的“动态对齐”。
*   **UI 数据驱动**: Web 前端（`app.js`）不应硬编码特定的配置 Key。例如，Prompt 模板下拉列表应完全由 `/api/project/prompt_templates` 接口返回的数据动态渲染。

### 3. 并发安全与数据一致性 (Concurrency Safety)
*   **内存读写锁**: `DataManager` 内置了 `threading.Lock()`，所有的 `load()` 和 `save()` 操作均处于线程锁保护下，确保磁盘写入的原子性与内存状态的一致性。
*   **深拷贝 Schema**: 调用 `get_project_data` 创建新项目时必须执行 `copy.deepcopy(DEFAULT_SCHEMA)`，防止列表/字典等引用类型在多项目间意外共享。
*   **原子写入**: 配置保存采用**原子重命名策略** (写入 `.json.tmp` 后调用 `os.replace` 覆盖)。这确保了即使在极端情况 (如进程意外中断) 下，配置文件也不会被截断或损坏。
*   **跨平台 IO 分发**: 避免直接使用如 `os.startfile` 等强依赖系统的 API。所有的原生系统调用均已抽象入 `FileUtils.open_path_in_os`，依据 `sys.platform` 进行动态分发。
*   **路径归一化强制标准 (v5.3 PRO)**: 为了解决 Windows 大小写不敏感及正反斜杠混用导致的 `KeyError` 或 `403` 误报，**所有内存中的字典键（Dictionary Keys）必须且只能使用 `PathValidator.norm_path` 处理后的字符串。**
*   **前端通信标准 (_fetch)**: `app.js` 必须一致性地调用 `App._fetch` 而非原生 `fetch`。这一封装确保了 HTTP 非 200 系列的状态码能被捕获并转化为人类可读的 UI Toast 提示，避免 API 拦截引发的静默失败。

### 4. 文件操作与快速分类 (FileOps & Quick Categorization)
*   **文件操作**: 实现了安全的文件移动、删除和归档功能。
*   **快速分类**: `batch_categorize` 模块允许基于规则对文件进行批量排序和分类。

### 5. 动作桥接 (ActionBridge)
*   **模板引擎**: ActionBridge 是一个模板引擎，用于在暂存文件上执行外部命令行工具 (CLI)。
*   **上下文注入**: 支持将文件路径、项目根目录、文件扩展名等上下文信息注入到 CLI 命令中，实现高度灵活的自动化操作。

### 6. UI 层 (UI Layer)
*   **解耦设计**: Tkinter 和 FastAPI 接口是解耦的，允许独立开发和部署。

## 🧪 测试方法论
本项目坚持 **100% 核心路径覆盖** 且遵循 **“零硬编码”原则**。
*   **测试隔离与自修复 (v5.3)**: `conftest.py` 引入了 `autouse` fixture，在每个测试运行前后强制重置 `DataManager` 单例和缓存，彻底消除测试间的交叉污染。
*   **测试隔离规范**: **严禁在单项测试中重写 `TestClient` 或 `DataManager` 实例。** 所有的测试必须共享 `conftest.py` 提供的隔离配置文件 `api_test_config.json`，以防止泄露至用户的真实配置目录。
*   **参数矩阵覆盖 (Matrix Testing)**: 在 `test_search.py` 中覆盖了搜索模式、正反向、大小写、排除规则的组合。
*   **零硬编码 (Zero Hardcoding)**: 测试 Fixture 严禁出现绝对路径。使用 `system_dir` 等动态感知 Fixture，确保测试在任何环境下皆能“动态对齐”。
*   **端到端工作流 (E2E)**: `test_e2e.py` 模拟了从“打开项目 -> 搜索并暂存 -> 选择模板 -> 生成上下文”的完整 AI 辅助心流。
*   **Mock 边界**: 使用 `pytest` 对 PowerShell 或 subprocess 调用进行隔离 Mock，确保逻辑验证不依赖于特定宿主环境的权限。
*   **并发压力测试**: 对核心引擎（如自适应检索、配置读写锁）进行 Stress Testing 覆盖。
*   **测试运行**: 
    ```bash
    python -m pytest
    ```
    v5.3 版本共包含 **80+** 项自动化测试用例。

## 🛠️ 打包与分发
*   **桌面版**: 使用 `build_exe.py` (封装了 PyInstaller) 进行单文件打包。
*   **网页版**: 基于 FastAPI，由于前端依赖 CDN (Bootstrap/Highlight.js)，部署时需确保网络连通性或将其本地化。

## 📝 贡献准则
1.  **KISS 原则**: 优先通过内置库解决问题，减少不必要的第三方依赖。
2.  **防御性编程**: 对所有涉及 `root` 以外的 IO 操作直接进行 `is_safe` 熔断处理。
