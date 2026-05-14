# FileCortex 测试说明

> **测试数**: 348 | **状态**: All Passed | **Ruff**: 0 errors

本项目包含 **348** 项核心全自动化的 `pytest` 测试，采用 **领域驱动深度加固 (Domain-Driven Hardening)** 架构，实现了从底层 IO 到上层 API 契约、前端契约、CLI 与 MCP 的全方位覆盖。

## 测试分层架构

| 层次 | 模块/文件 | 测试数 | 覆盖范围 |
|------|-----------|--------|----------|
| **BUG修复 & 边界** | `test_bugfix_v632.py` | 54 | v6.3.2 全量回归: CLI分支/配置API/搜索/路径/文件/噪声/格式/DI/Web API |
| **CLI 层** | `test_comprehensive_v63.py::TestCLI` | 5 | `fctx.py` open/stage/projects/拒绝系统目录 |
| **MCP 协议层** | `test_comprehensive_v63.py::TestMCPServer` + `test_mcp_server.py` | 14 | 搜索/注册/蓝图/列表/上下文/统计 |
| **Web API 层** | `test_web_api_advanced.py` + `test_web_endpoints.py` + `test_comprehensive_v63.py::TestWebAPIExtended` | 43 | CRUD/CORS/Auth/设置/异常处理/参数对齐 |
| **WebSocket 层** | 内嵌于 Web API 测试 | 5 | 搜索协议/Auth/参数矩阵/工具流 |
| **核心引擎层** | `test_search_engine.py` + `test_dm_config.py` + `test_fileops_advanced.py` + `test_security_resilience.py` + `test_context_formatter.py` + `test_utils_format.py` + `test_comprehensive_v63.py` | 180+ | 搜索矩阵/配置管理/文件操作/安全沙盒/上下文/格式化 |
| **集成层** | `test_core_integration.py` + `test_scenarios.py` + `test_ai_enhanced.py` | 25 | 编码回弹/级联回滚/完整流程/路径收集 |
| **前端契约层** | `test_frontend_contract.py` | 7 | HTML/JS/CSS/Desktop GUI 结构/路由模块 |
| **Duplicate** | `test_comprehensive_v63.py::TestDuplicateWorkerExtended` | 2 | 取消扫描/空目录 |
| **总计** | | **348** | **100% 关键路径** |

## v6.3.2 新增测试清单

| # | 测试类 | 测试数 | 关键覆盖 |
|---|--------|--------|----------|
| 1 | TestFctxElseBranch | 4 | CLI else 分支逻辑回归 |
| 2 | TestHttpRoutesConfigAPI | 2 | 强类型 config API 验证 |
| 3 | TestSearchEdgeCases | 4 | 空结果/中断/大文件/内容匹配 |
| 4 | TestContextBlueprint | 2 | 蓝图路径类型兼容 |
| 5 | TestGUIImportSafety | 4 | GUI 导入 + PathCollectionDialog |
| 6 | TestPathValidatorEdgeCases | 5 | None/空/尾部斜杠/空root |
| 7 | TestFileOpsEdgeCases | 6 | 原子保存/移动/归档/分类 |
| 8 | TestNoiseReducerEdgeCases | 4 | None/空/base64/正常行 |
| 9 | TestFormatUtilsEdgeCases | 6 | 负数/零/GB/CJK |
| 10 | TestDataManagerEdgeCases | 5 | DI/部分更新/类型验证/去重/session |
| 11 | TestWebAPIEdgeCases | 7 | 设置轮询/上下文/staging/保存 |
| 12 | TestContextFormatterEdgeCases | 5 | 空/CDATA/prefix/noise |

## 参数对齐测试矩阵

| 参数 | 前端定义 | 后端模型 | 验证测试 |
|------|----------|----------|----------|
| `token_threshold` | `state.js:20` (128000) | `GlobalSettings.token_threshold` | `test_global_settings_handles_settings_alias` |
| `preview_limit_mb` | `main.js:260` | `GlobalSettings.preview_limit_mb` | `test_global_settings_roundtrip` |
| `allowed_extensions` | `main.js:263` | `GlobalSettings.allowed_extensions` | `test_global_settings_handles_allowed_extensions` |
| `apply_noise_reducer` | `schemas.py:30` | `GenerateRequest` → `ContextFormatter` | `test_api_generate_with_noise_reducer` |
| `api_token` | `window.__FCTX_API_TOKEN__` | env `FCTX_API_TOKEN` | `test_api_token_header_forward` |
| Version | `{{ version }}` | `__version__` = "6.3.1" | `test_api_index_page_injects_version` |

## 运行指令

```bash
# 全量测试
python -m pytest

# 按测试文件
python -m pytest tests/test_comprehensive_v63.py

# 按标记执行
python -m pytest tests/ -m "not slow"

# 并发加速
python -m pytest -n auto tests/
```

## 测试架构原则

1. **隔离性**: 每个测试通过 `_reset_singleton` fixture 获得独立的 `DataManager` 实例
2. **可重现性**: 所有文件操作使用 `tmp_path` fixture 保证临时目录
3. **进程清理**: `conftest.py` 自动清理遗留的 Popen 进程
4. **Windows 兼容**: 测试通过 0.2s 休眠确保文件锁释放
