# FileCortex 参数一致性与动态对齐审计报告 (v6.3.0)

## 1. 概述
在 v6.3.0 的重构中，我们重点解决了桌面端 (Tkinter)、Web 端 (FastAPI/ES6) 与核心库 (file_cortex_core) 之间的参数同步问题。本文档记录了关键参数的流转逻辑与对齐机制。

## 2. 核心参数对齐矩阵

| 参数项 | 核心库定义 (`DataManager`) | 桌面端实现 (`file_search.py`) | Web 端实现 (`state.js` / `schemas.py`) | 对齐机制 |
| :--- | :--- | :--- | :--- | :--- |
| **预览上限 (MB)** | `global_settings["preview_limit_mb"]` | `get_preview_limit()` 从 DM 读取 | `state.config.previewLimit` (API 同步) | 统一由 `DataManager.load()` 初始化，UI 渲染时动态查询 |
| **Token 比例** | `global_settings["token_ratio"]` | 用于状态栏实时计算 | `state.config.tokenRatio` | 后端 `/api/global/settings` 接口强对齐 |
| **搜索模式** | `search_mode` (smart/exact/regex/content) | `search_mode_var` (Tkinter) | `state.searchMode` (Select) | 共享 `search_generator` 的枚举值校验 |
| **忽略规则** | `excludes` (string list) | `exclude_var` 同步至项目配置 | `state.projConfig.excludes` | 持久化于 `config.json`，两端加载时均执行 `PathValidator.norm_path` |
| **Token 预警阈值**| `token_threshold` | UI 变红显示 (配置驱动) | UI 进度条显示 | 已统一整合至全局设置，由 DataManager 集中分发 |

## 3. 动态对齐机制实现

### 3.1 后端：基于 Pydantic 的 Schema 守卫
所有 API 接口均使用 `routers.schemas` 中定义的模型。
*   **强制校验**：例如 `SearchRequest` 强制要求 `project_path` 必须存在且经过归一化。
*   **默认值同步**：API 默认值与核心库 `DataManager.DEFAULT_SCHEMA` 保持严格一致。

### 3.2 前端：基于模块化的状态中心
*   **SSOT (Single Source of Truth)**：`static/js/state.js` 存储从 API 获取的最新的项目配置和全局设置。
*   **动态拉取**：Web 页面初始化时调用 `api.fetchGlobalSettings()`，确保 UI 控件值与后端完全同步。

### 3.3 路径一致性协议 (Normalization Protocol)
所有涉及文件路径的参数必须经过 `PathValidator.norm_path` 处理：
1.  **转换斜杠**：所有 `\` 转换为 `/`。
2.  **强制小写 (Windows)**：解决驱动器盘符大小写不一致导致的匹配失效。
3.  **去除尾随斜杠**：确保目录匹配的唯一性。

## 4. 测试与验证

### 4.1 自动化测试覆盖
*   **`test_api_v6.py`**：验证前端请求参数经过 API 层解析后，能正确传递给核心搜索引擎。
*   **`test_dm_config.py`**：验证配置项在不同入口修改后，持久化结果的一致性。
*   **`test_security_path.py`**：验证各种边界情况下的路径对齐逻辑。

### 4.2 审计结论
通过本次重构，FileCortex 已消除大部分硬编码参数。目前的参数架构支持：
- **热更新**：修改全局设置后，两端界面在下次操作或刷新后立即生效。
- **配置自愈**：如果 `config.json` 缺少字段，系统会自动补全为对齐的默认值。
