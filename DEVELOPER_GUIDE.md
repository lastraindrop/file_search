# FileCortex - 开发者指南

> **版本**: 6.4.0 | **更新日期**: 2026-05-24

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
*   `file_cortex_core.process_utils`: 跨平台进程终止工具 — 从 `action_routes.py`, `ws_routes.py`, `common.py` 三处重复逻辑中提取，统一 `terminate_process()` / `cleanup_processes()` 模式。

### 1.4 路由层架构 (v6.3.2)
HTTP 路由已按功能域拆分：

```
routers/
├── http_routes.py        # 合并层 (27 行, 向后兼容)
├── project_routes.py     # 工作区/项目管理 (201 行)
├── fs_routes.py          # 文件系统 CRUD (310 行)
├── action_routes.py      # 暂存/工具执行/上下文/设置 (252 行, 进程终止逻辑已提取)
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
| `wsSearch` | `state.js:config.endpoints.wsSearch` | `ws_routes.py` `/ws/search` | WebSocket URL | `test_ws_search_endpoint` |
| `wsExecute` | `state.js:config.endpoints.wsExecute` | `ws_routes.py` `/ws/execute` | WebSocket URL | `test_ws_execute_endpoint` |

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
2. **Pytest**: `python -m pytest` (验证 **479** 项核心测试)

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
- [ ] 所有 WebSocket 处理器中 `JSON.parse()` 已用 try/catch 保护
- [ ] 所有 `innerHTML` 赋值已用 `escapeHtml()` 包装器保护

---

## 3. 安全基线
*   **路径沙盒**: 所有外部路径输入必须通过 `PathValidator.is_safe`。
*   **注入防御**: `ActionBridge` 使用 `subprocess.run(list_args)` 避免 shell 注入风险。
*   **Token 审计**: 生产环境下所有 `/api/` 及 `/ws/` 请求均需通过 Token 校验（HTTP `X-API-Token` header + WebSocket `token` query param）。
*   **XSS 防御 (前端)**: `marked.parse()` 配置 sanitizer 选项；所有用户控制的 `innerHTML` 赋值经过 `escapeHtml()` 包装器处理；集中化 `_post()`/`_postJson()` 降低分散 fetch 调用引入注入的风险。
*   **WebSocket 健壮性**: 所有 `onmessage` 中 `JSON.parse()` 使用 try/catch 保护；`onerror` 不再静默返回 false success。

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

## 5. 前端架构 (v6.4.0)

### 5.1 API 层模式
`static/js/api.js` 采用集中化的请求辅助方法：

```javascript
// _post(url, data) — 标准 POST, 返回 JSON
async _post(url, data) { ... }

// _postJson(url, json) — JSON 序列化 POST, 返回 JSON
async _postJson(url, json) { ... }
```

所有 API 端点调用通过这两个辅助方法统一管理，消除分散的 `fetch()` 调用。

### 5.2 端点集中管理
所有后端端点 URL 集中在 `static/js/state.js` 的 `config.endpoints` 对象中：
- 4 个新 WebSocket 端点 key 已添加
- `wsSearch`, `wsExecute` 等通过 `config.endpoints` 统一引用
- 新增端点只需修改一处，前端全局生效

### 5.3 关键 UI 模式
- **actionModal**: 自定义确认对话框组件，替代所有原生 `confirm()` 调用
- **标签管理**: 前端 UI 支持添加/移除标签，无需刷新页面
- **文件创建**: 模态框驱动的文件创建流程
- **debounced sync**: `syncStagingToBackend` 使用 debounce 减少频繁 API 调用
- **可折叠面板**: 左面板基于可折叠区域而非 Bootstrap 标签页

---

## 6. 测试架构

```
tests/
├── conftest.py                      # 共享 fixtures + DataManager.reset()
├── test_bugfix_v633.py              # v6.3.3 新增 24 项测试 (BUG修复/边界/Google Style)
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

## 7. v6.4.0 变更摘要

| 类别 | 变更 |
|------|------|
| **安全** | 3 处 XSS 修复 (marked sanitization, escapeHtml, api.js 集中化); WS JSON.parse try/catch; WS onerror 修复 |
| **重构** | process_utils.py 跨平台进程终止 (3 处去重); api.js _post/_postJson 集中化 |
| **类型** | 14 处裸泛型 → 参数化泛型 (7 文件); self.q→self.query 等命名修复; stop_event 类型修正 |
| **前端** | 可折叠左面板; staging 加宽 col-md-3; tag 管理; file 创建; SRI 哈希; confirm→actionModal; debounced sync |
| **CSS/HTML** | .pulse-warning 添加; 重复 CSS 合并; 未使用规则移除; aria-live/aria-label 可访问性 |
| **测试** | +107 项 (总计 479) / ruff 0 errors |
