# AI Context Workbench - 开发者指南 (DEVELOPER_GUIDE)

欢迎参与 AI Context Workbench 的开发。本项目采用核心逻辑 (`core_logic.py`) + 多端适配 (`file_search.py`, `web_app.py`) 的分层架构。

## 🏗️ 核心架构

### 1. 权限与安全校验
为了防止路径越权（Path Traversal），本项目采用了 **注册制**。
*   只有通过 `/api/open` 显式注册的目录才能作为 `project_root`。
*   所有的文件读写、列表、搜索操作必须通过 `get_valid_project_root(path)` 进行二次验证。
*   **规范**: 禁止使用 `os.path.join` 处理未经过滤的用户输入路径，一律使用 `pathlib` 结合 `is_safe` 方法。

### 2. 参数一致性与动态对齐 (Consistency)
由于项目同时维护桌面版 (Tkinter) 和网页版 (FastAPI)，保持参数一致性至关重要：
*   **核心配置**: 统一存储在 `DataManager.data["projects"]` 下。
*   **同步机制**: 任何新增的过滤参数（如 `excludes`, `case_sensitive`）必须在 `core_logic.SearchWorker` 和 `web_app.websocket_search` 中同步更新参数列表。
*   **Pydantic 模型**: Web 端使用 Pydantic 进行强类型检查，桌面端则使用变量绑定。

## 🧪 测试方法论
本项目坚持 **100% 关键路径覆盖**。
*   **Mock 系统**: 使用 `pytest` 配合 `unittest.mock` 对操作系统级指令（如 PowerShell）进行隔离测试。
*   **跨平台兼容**: 在编写路径逻辑时，优先使用 `pathlib` 的 `forward slash` 转换，确保在 Windows 和 Linux 下行为一致。
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
