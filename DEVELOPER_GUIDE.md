# FileCortex - 开发者指南

> **版本**: 6.5.1 | **更新日期**: 2026-06-15 | **测试**: 768 passed | **Ruff**: 0 errors | **Google Style**: 全规范审计完成

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
*   `file_cortex_core.context`: AI 上下文生成（Markdown/XML），支持 `apply_noise_reducer` 参数控制去噪；OOM 保护 (500文件/50MB上限)。
*   `file_cortex_core.file_io`: `FileUtils.walk_filtered()` — 统一的项目目录遍历生成器，所有 os.walk 调用点共享。
*   `file_cortex_core.process_utils`: 跨平台进程终止工具。
*   `file_cortex_core.actions`: `FileOps` (文件操作) + `ActionBridge` (工具桥接)，支持 DataManager DI。
*   `file_cortex_core.config`: `DataManager` (SSOT 配置中心) + `GlobalSettings`/`ProjectConfig` (Pydantic 模型)。

### 1.4 路由层架构
HTTP 路由已按功能域拆分：

```
routers/
├── http_routes.py        # 合并层 (向后兼容)
├── project_routes.py     # 工作区/项目管理
├── fs_routes.py          # 文件系统 CRUD
├── action_routes.py      # 暂存/工具执行/上下文/设置
├── ws_routes.py          # WebSocket 搜索/工具流
├── schemas.py            # Pydantic 请求模型
├── services.py           # 业务逻辑服务层
└── common.py             # ProcessManager (线程安全进程容器, 容量限制50)
```

所有子路由通过 `http_routes.py` 合并为单一 `router` 对象，`web_app.py` 和测试代码无需变更。

### 1.5 前后端参数动态对齐
前后端关键参数通过统一校验机制保持一致性：

| 参数 | 前端定义 | 后端模型 | 传输路径 | 验证测试 |
|------|----------|----------|----------|----------|
| `token_threshold` | `state.js` (128000) | `GlobalSettings.token_threshold` | `/api/global/settings` | `test_global_settings_handles_settings_alias` |
| `preview_limit_mb` | `main.js` | `GlobalSettings.preview_limit_mb` | `/api/global/settings` | `test_global_settings_roundtrip` |
| `allowed_extensions` | `main.js` | `GlobalSettings.allowed_extensions` | `/api/global/settings` | `test_global_settings_handles_allowed_extensions` |
| `apply_noise_reducer` | `schemas.py` | `GenerateRequest` | `/api/generate` | `test_api_generate_with_noise_reducer` |
| `api_token` | `window.__FCTX_API_TOKEN__` | `web_app.py` | HTTP `X-API-Token` + WS `token` | `test_api_token_header_forward` |
| 版本号 | `index.html` `{{ version }}` | `file_cortex_core/__init__.py` | Jinja2 模板注入 | `test_api_index_page_injects_version` |
| `wsSearch` | `state.js:config.endpoints.wsSearch` | `ws_routes.py` `/ws/search` | WebSocket URL | `test_ws_search_endpoint` |
| `wsExecute` | `state.js:config.endpoints.wsExecute` | `ws_routes.py` `/ws/actions/execute` | WebSocket URL | `test_ws_execute_endpoint` |

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
1. **Ruff**: `ruff check .` (强制执行 D, I, N, B, UP, RET, C4, SIM 等规则 + Google pydocstyle)
2. **Pytest**: `python -m pytest` (验证 **764** 项核心测试)

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
- [ ] `logger.exception()` 而非 `logger.error(f"...{e}")` 用于异常日志
- [ ] 公共函数完成完整类型注解 (参数 + 返回值)

---

## 3. 安全基线
*   **路径沙盒**: 所有外部路径输入必须通过 `PathValidator.is_safe`。
*   **注入防御**: `ActionBridge` 使用 `subprocess.run(list_args)` 避免 shell 注入风险。
*   **Token 审计**: 生产环境下所有 `/api/` 及 `/ws/` 请求均需通过 Token 校验。
*   **XSS 防御 (前端)**: `marked.parse()` 配置 sanitizer 选项；所有用户控制的 `innerHTML` 赋值经过 `escapeHtml()` 包装器。
*   **WebSocket 健壮性**: 所有 `onmessage` 中 `JSON.parse()` 使用 try/catch 保护。

---

## 4. API 认证流程

```
客户端请求:
  HTTP:  Header X-API-Token → web_app.py middleware → 验证
  WS:    query ?token=xxx     → ws_routes.py verify_ws_token → 验证

Token 来源:
  window.__FCTX_API_TOKEN__  ← index.html Jinja2 注入 ← web_app.py api_token
  state.globalSettings.api_token  (备用路径，通常为空)
```

---

## 5. 前端架构

### 5.1 API 层模式
`static/js/api.js` 采用集中化的请求辅助方法：

```javascript
// _post(url, data) — 标准 POST, 返回 JSON
async _post(url, data) { ... }

// _postJson(url, json) — JSON 序列化 POST, 返回 JSON
async _postJson(url, json) { ... }
```

### 5.2 端点集中管理
所有后端端点 URL 集中在 `static/js/state.js` 的 `config.endpoints` 对象中。
新增端点只需修改一处，前端全局生效。

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
├── test_v8_comprehensive.py         # v6.4.0+/v6.5.0 新增 77 项测试 (DI/OOM/CLI/ProcessManager)
├── test_coverage_fill.py            # v6.5.0 新增 20 项测试 (process_utils/ProcessManager)
├── test_security_fixes_v650.py       # v6.5.0 新增 38 项安全修复测试
├── test_frontend_contract.py        # v6.5.0+ 前端契约测试 (共 32 项)
├── test_bugfix_v7.py                # v6.4.0 回归测试 (BUF/前端/WebSocket)
├── test_bugfix_v633.py              # v6.3.3 BUG修复 + 边界覆盖
├── test_bugfix_v632.py              # v6.3.2 BUG修复 + 边界覆盖
├── test_comprehensive_v63.py        # v6.3.1 全量 CLI/MCP/Web/安全测试
├── test_comprehensive.py            # 核心功能 + 高级边界
├── test_dm_config.py                # 配置管理 (dm.data→dm.config 迁移验证)
├── test_security_resilience.py      # 安全沙盒
├── test_search_engine.py            # 搜索引擎矩阵
├── test_fileops_advanced.py         # 文件操作
├── test_web_api.py                  # Web API (v6.5.0 TC-2 合并)
├── test_core_integration.py         # 集成测试
├── test_mcp_server.py               # MCP 协议
├── test_additional_coverage.py      # 边缘覆盖
├── test_ai_enhanced.py              # AI 上下文/Blueprint
├── test_context_formatter.py        # XML/MD 导出
├── test_utils_format.py             # 格式化/Token估算
├── test_scenarios.py                # 端到端场景
├── test_packaging.py                # v6.5.1 新增 — 打包完整性 (15)
├── test_security_v9.py              # v6.5.1 新增 — P0/P1 安全回归 (17)
```

## 7. v6.5.0 变更摘要

| 类别 | 变更 |
|------|------|
| **Google Style 审计** | 23 处 logger f-string 异常日志→`logger.exception()`；22 处冗余 `as e` 清理；8 处类型注解补全；5 文件 import 排序修复；2 处 `__main__`→`main()` 规范化；1 处 `format` 遮蔽修复 |
| **CLI 增强** | `fctx search` (smart/exact/regex/content) + `fctx export` (markdown/xml, --output) |
| **OOM 保护** | `context.py` 新增 `MAX_EXPORT_FILES=500` + `MAX_TOTAL_CONTENT_BYTES=50MB` |
| **进程管理** | `routers/common.py` ProcessManager 封装 (线程安全、容量50、旧API别名) |
| **前端修复** | 8 项修复 (stageAll CRITICAL BUG、上下文菜单越界、bulkActions 死代码、tree-node 选择器污染等) |
| **测试** | +118 项 (总计 629) / ruff 0 errors / Google Style 全项通过 |
| **弃用 API** | 14 处 `dm.data[...]` → `dm.config.xxx` 迁移 |
| **硬编码** | 版本号 `"6.5.0"` → `core_version` 动态导入；默认值 `== 128000` → `GlobalSettings()` |
| **线程安全** | `SearchWorker`/`DuplicateWorker` daemon=True 构造器传参 |

### v6.5.0 安全加固与前端优化 (2026-06-07)

| 类别 | 变更摘要 |
|------|----------|
| **安全修复** | 5 项：符号链接遍历防护 (BUG-1)、访问控制绕过修复 (BUG-2)、DataManager 线程安全 (BUG-3/4)、MCP/CLI 入口统一验证 (BUG-5/11) |
| **后端修复** | 3 项：不可达代码移除 (BUG-6)、stats 内存限制 (BUG-7)、ProcessManager 封装 (BUG-8) |
| **前端 XSS** | DOMPurify 3.1.6 + SRI 替代手工过滤 (BUG-MD-XSS) |
| **前端优化** | 8 项：Ctrl+S 双保存、三栏布局 11/12→12/12、搜索 snippet、模态框堆叠、100dvh、CSS 变量统一、侧边栏单一数据源、状态管理清理 |
| **测试整合** | 6 精确重复项移除；Web API 3→1 文件合并；硬编码值动态化；+38 安全测试 (test_security_fixes_v650.py) |
| **测试** | +32 项 (总计 629) / 文件 23→21 / ruff 0 errors / 全部通过 |

### v6.5.1 部署加固与安全补强 (2026-06-15)

| 类别 | 变更摘要 |
|------|----------|
| **部署修复 (P0)** | `pyproject.toml` 打包补全 `routers`/`mcp_server`/`build_exe`；`mcp` 可选依赖组 + README 安装说明；`fctx-mcp` 控制台脚本 |
| **安全修复 (P0)** | `api_categorize` 路径遍历修补；index 页 token 泄露修复 (`_is_local_request` 守卫)；mermaid CDN SRI 补齐 |
| **安全加固 (P1)** | 11 项输入字段 `max_length=1000`；dict 字段 `field_validator` 100KB 上限；token 比较 `hmac.compare_digest`；WS `search_task` finally 取消；ProcessManager PID 复用拒绝；`api_terminate_process` 用 Popen 终止 |
| **核心健壮性** | `to_xml` 日志；`archive_selection` 目录分支 arcname；Windows 长路径剥离；`batch_rename` `count` 参数；search pool shutdown 检查；SearchWorker 异常入队 |
| **前端** | `ctxAction` try/finally 状态恢复；Bootstrap 5.3 / marked 12.0 / DOMPurify 3.1.6 / mermaid 10.9 SRI 全链完整性校验 |
| **测试** | +32 项 (test_packaging 15 + test_security_v9 17) + 当前稳定化/copy-extract/批量copy+事务extract+progress 回归 / 总计 764 / ruff 0 / 全部通过 |
| **文档** | 全文档版本号 6.5.0→6.5.1 同步；TECHNICAL_GUIDE 过时测试文件引用修正；ROADMAP v6.5.1 章节 + v7.0 计划更新 |
