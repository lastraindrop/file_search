# FileCortex - 开发者指南

> **版本**: 6.3.2 | **更新日期**: 2026-05-14

欢迎参与 FileCortex 的开发。本项目采用微内核架构，致力于构建一个本地优先、AI 友好的工作区编排工具。

---

## 1. 架构设计

### 1.1 配置管理 (SSOT)
`DataManager` 是系统的状态中心。基于 **Pydantic V2** 模型驱动。

*   **模型访问**: 推荐使用 `DataManager().config` 访问强类型对象（如 `config.global_settings.token_threshold`）。
*   **兼容性**: `.data` 属性提供字典视图，标记为 DEPRECATED——新代码应使用 Pydantic 模型属性。
*   **原子性**: 所有修改必须通过 `dm.update_*` 方法并调用 `dm.save()` 完成持久化。

### 1.2 依赖注入 (v6.3.2)
`DataManager` 支持三种实例管理模式：

```python
# 1. 单例访问 (默认, 向后兼容)
dm = DataManager()

# 2. 独立实例 (测试/DI 场景)
dm = DataManager.create()

# 3. 上下文管理器 (临时替换全局单例)
with DataManager.activate(dm):
    service = SomeService(DataManager())

# 4. 重置单例 (测试隔离)
DataManager.reset()
```

### 1.3 核心模块
*   `file_cortex_core.security`: `PathValidator` 提供唯一性路径归一化协议。
*   `file_cortex_core.search`: 匹配逻辑与文件系统遍历完全解耦，策略化设计。
*   `file_cortex_core.context`: AI 上下文生成（Markdown/XML），支持 `apply_noise_reducer` 参数控制去噪。
*   `file_cortex_core.file_io`: `FileUtils.walk_filtered()` — 统一的项目目录遍历生成器，所有 os.walk 调用点共享。

### 1.4 路由层架构 (v6.3.2)
HTTP 路由已按功能域拆分：

```
routers/
├── http_routes.py        # 合并层 (27 行, 向后兼容)
├── project_routes.py     # 工作区/项目管理 (201 行)
├── fs_routes.py          # 文件系统 CRUD (310 行)
├── action_routes.py      # 暂存/工具执行/上下文/设置 (278 行)
├── ws_routes.py          # WebSocket 搜索/工具流
├── schemas.py            # Pydantic 请求模型
├── services.py           # 业务逻辑服务层
└── common.py             # 共享状态与进程管理
```

所有子路由通过 `http_routes.py` 合并为单一 `router` 对象，`web_app.py` 和测试代码无需变更。

### 1.5 前后端参数动态对齐
前后端关键参数通过统一校验机制保持一致性：

| 参数 | 前端定义 | 后端模型 | 传输路径 | 验证测试 |
|------|----------|----------|----------|----------|
| `token_threshold` | `state.js:20` (128000) | `GlobalSettings.token_threshold` | `/api/global/settings` | `test_global_settings_handles_settings_alias` |
| `preview_limit_mb` | `main.js:260` | `GlobalSettings.preview_limit_mb` | `/api/global/settings` | `test_global_settings_roundtrip` |
| `allowed_extensions` | `main.js:263` | `GlobalSettings.allowed_extensions` | `/api/global/settings` | `test_global_settings_handles_allowed_extensions` |
| `apply_noise_reducer` | `schemas.py:30` | `GenerateRequest` | `/api/generate` | `test_api_generate_with_noise_reducer` |
| `api_token` | `index.html:430` → `window.__FCTX_API_TOKEN__` | `web_app.py:22` | HTTP `X-API-Token` + WS `token` | `test_api_token_header_forward` |
| 版本号 | `index.html:8,25` → `{{ version }}` | `file_cortex_core/__init__.py:3` | Jinja2 模板注入 | `test_api_index_page_injects_version` |

**对齐原则**: 添加新参数时，必须同步更新：
1. 前端 `state.js`/`defaults` 或对应 form 字段
2. 后端 Pydantic 模型字段
3. Schema/Request 模型
4. 对应的 API route 处理逻辑
5. 新增单元测试覆盖参数传递链路

---

## 2. 规范与标准 (Code Standards)

本项目严格执行 **Google Python Style Guide**。

### 2.1 自动化检查
1. **Ruff**: `ruff check .` (强制执行 D, I, N, B, UP, RET, C4, SIM 等规则)
2. **Pytest**: `python -m pytest` (验证 **348** 项核心测试)

### 2.2 Docstrings 样例
```python
def example_method(path: str) -> bool:
    """Example Google-style docstring.

    Args:
        path: Description of the input path.

    Returns:
        True if operation was successful.

    Raises:
        OSError: If file system access fails.
    """
```

### 2.3 提交前检查清单
- [ ] `ruff check .` 0 errors
- [ ] `python -m pytest` 全部通过
- [ ] 新增参数已在前端/后端/Schema 三方对齐
- [ ] 新增功能有对应单元测试
- [ ] 版本号统一（`__init__.py`, `pyproject.toml`）

---

## 3. 安全基线
*   **路径沙盒**: 所有外部路径输入必须通过 `PathValidator.is_safe`。
*   **注入防御**: `ActionBridge` 使用 `subprocess.run(list_args)` 避免 shell 注入风险。
*   **Token 审计**: 生产环境下所有 `/api/` 及 `/ws/` 请求均需通过 Token 校验（HTTP `X-API-Token` header + WebSocket `token` query param）。

---

## 4. API 认证流程

```
客户端请求:
  HTTP:  Header X-API-Token → web_app.py:49 middleware → 验证
  WS:    query ?token=xxx     → ws_routes.py:27 verify_ws_token → 验证

Token 来源:
  window.__FCTX_API_TOKEN__  ← index.html:430 Jinja2 注入  ← web_app.py:105 api_token
  state.globalSettings.api_token  (备用路径，通常为空)
```

---

## 5. 测试架构

```
tests/
├── conftest.py                      # 共享 fixtures + DataManager.reset()
├── test_bugfix_v632.py              # v6.3.2 新增 54 项测试 (BUG修复/边界/DI)
├── test_comprehensive_v63.py        # v6.3.1 新增 73 项测试 (CLI/MCP/Web/安全)
├── test_additional_coverage.py      # v6.3.0 新增 30 项边缘测试
├── test_dm_config.py                # 配置管理
├── test_security_resilience.py      # 安全沙盒
├── test_search_engine.py            # 搜索引擎
├── test_fileops_advanced.py         # 文件操作
├── test_web_api_advanced.py         # Web API
├── test_web_endpoints.py            # Web 端点
├── test_core_integration.py         # 集成测试
├── test_mcp_server.py               # MCP 协议
├── test_frontend_contract.py        # 前端结构契约
└── ...更多
```

## 6. v6.3.2 变更摘要

| 类别 | 变更 |
|------|------|
| **BUG** | fctx.py else 分支逻辑错误 / results_count 未初始化 / None 崩溃 / deprecated API |
| **重构** | 路由层按域拆分为 3 模块 / 共享 walk_filtered 遍历 / Clipboard 去重 / DataManager DI |
| **新增** | PathCollectionDialog 组件 / DataManager.create/reset/activate |
| **测试** | +54 项 (总计 348) / ruff 0 errors |
