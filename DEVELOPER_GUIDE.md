# AI Context Workbench - 开发者指南 (DEVELOPER_GUIDE)

欢迎参与 AI Context Workbench 的开发。本项目采用核心逻辑 (`core_logic.py`) + 多端适配 (`file_search.py`, `web_app.py`) 的分层架构。

## 🏗️ 核心架构

### 1. 权限与安全校验
为了防止路径越权 (Path Traversal) 和 XSS 攻击，本项目采用了严格的校验机制：
*   **路径权限注册制**: 只有通过 `/api/open` 显式注册的目录才能作为 `project_root`。
*   **黑名单保护**: `PathValidator` 采用路径组件精准匹配，拦截对 `Windows`, `System32`, `etc` 等系统关键目录的直接访问。
*   **文件名隔离**: 在重命名和归档操作中，严格限制文件名不得包含路径分隔符。
*   **XSS 防护**: Web 前端在渲染任何用户可控的文件名/路径时，必须通过 `App.escapeHtml` 进行转义，禁止直接使用 `.innerHTML` 拼接。
*   **规范**: 禁止使用 `os.path.join` 处理未经过滤的用户输入路径，一律使用 `pathlib` 结合 `is_safe` 方法。

### 2. 参数一致性与动态对齐 (Consistency)
保持跨端 (Tkinter/Web) 参数一致性是维护的核心：
*   **无状态 API (Statelessness)**: Web 端接口严禁依赖后台全局变量（如 `last_project`）。所有文件操作必须显式传递 `project_path`，以支持多标签页并发。
*   **Schema 动态对齐**: `DataManager.get_project_data` 在加载配置时，会自动对比 `DEFAULT_SCHEMA` 并补全缺失字段（如 `staging_list`, `notes`），确保旧版配置无缝升级至最新架构。
*   **数据一致性**: 待处理清单 (Staging) 变动时需立即调用持久化接口，确保在异常崩溃或跨端切换时数据不丢失。
*   **Pydantic 模型**: Web 端强制使用 Pydantic 提供严格的入参类型校验。

### 3. 并发安全与数据一致性 (Concurrency Safety)
*   **线程锁**: `DataManager` 内置了 `threading.Lock()`，所有的 `load` 和 `save` 操作均处于线程安全上下文中，防止多端或高频 API 请求引发的竞态条件。
*   **原子写入**: 配置保存采用**原子重命名策略** (写入 `.json.tmp` 后调用 `os.replace` 覆盖)。这确保了即使在极端情况 (如进程意外中断) 下，配置文件也不会被截断或损坏。
*   **跨平台 IO 分发**: 避免直接使用如 `os.startfile` 等强依赖系统的 API。所有的原生系统调用均已抽象入 `FileUtils.open_path_in_os`，依据 `sys.platform` 进行动态分发。

## 🧪 测试方法论
本项目坚持 **100% 关键路径覆盖**。
*   **Mock 系统**: 使用 `pytest` 配合 `unittest.mock` 对操作系统级指令（如 PowerShell）进行隔离测试。
*   **跨平台 Fixtures**: 测试用例内部严禁硬编码特定的操作系统路径（如 `C:/Windows`）。采用动态路径生成与 `mock.patch` 探测相结合，确保测试可以在任何 OS 甚至无环境磁盘上运行，杜绝 False Negative。
*   **并发压力测试**: 对核心引擎（如多线程搜索、配置读写锁）进行高强度并发（Stress Testing）覆盖。
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
