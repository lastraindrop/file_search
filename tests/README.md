# FileCortex 测试说明

> **测试数**: 294 | **状态**: All Passed | **Ruff**: 0 errors

本项目包含 **294** 项核心全自动化的 `pytest` 测试，采用 **领域驱动深度加固 (Domain-Driven Hardening)** 架构，实现了从底层 IO 到上层 API 契约、前端契约、CLI 与 MCP 的全方位覆盖。

## 测试分层架构

| 层次 | 模块/文件 | 测试数 | 覆盖范围 |
|------|-----------|--------|----------|
| **CLI 层** | `test_comprehensive_v63.py::TestCLI` | 5 | `fctx.py` open/stage/projects/拒绝系统目录 |
| **MCP 协议层** | `test_comprehensive_v63.py::TestMCPServer` + `test_mcp_server.py` | 14 | 搜索/注册/蓝图/列表/上下文/统计 |
| **Web API 层** | `test_web_api_advanced.py` + `test_web_endpoints.py` + `test_comprehensive_v63.py::TestWebAPIExtended` | 43 | CRUD/CORS/Auth/设置/异常处理/参数对齐 |
| **WebSocket 层** | 内嵌于 Web API 测试 | 5 | 搜索协议/Auth/参数矩阵/工具流 |
| **核心引擎层** | `test_search_engine.py` + `test_dm_config.py` + `test_fileops_advanced.py` + `test_security_resilience.py` + `test_context_formatter.py` + `test_utils_format.py` + `test_comprehensive_v63.py` | 180+ | 搜索矩阵/配置管理/文件操作/安全沙盒/上下文/格式化 |
| **集成层** | `test_core_integration.py` + `test_scenarios.py` + `test_ai_enhanced.py` | 25 | 编码回弹/级联回滚/完整流程/路径收集 |
| **前端契约层** | `test_frontend_contract.py` | 4 | HTML/JS/CSS/Desktop GUI 结构 |
| **Duplicate** | `test_comprehensive_v63.py::TestDuplicateWorkerExtended` | 2 | 取消扫描/空目录 |
| **总计** | | **294** | **100% 关键路径** |

## v6.3.1 新增测试清单

| # | 测试类 | 测试数 | 关键覆盖 |
|---|--------|--------|----------|
| 1 | TestCLI | 5 | fctx.py 首次覆盖 |
| 2 | TestMCPServer | 11 | MCP 全功能 |
| 3 | TestWebAPIExtended | 13 | Token/CORS/全局设置/production mode |
| 4 | TestPathValidatorExtended | 10 | UNC/POSIX/嵌套/系统目录 |
| 5 | TestFileOpsExtended | 11 | 原子保存/创建/移动/归档 |
| 6 | TestConfigExtended | 9 | 持久化/去重/验证/遍历阻止 |
| 7 | TestSearchExtended | 6 | 中断/取消/逆搜索/CDATA |
| 8 | TestNoiseReducerExtended | 3 | None/空/混合 |
| 9 | TestFormatUtilsExtended | 3 | 分隔符/前缀后缀/数字 |
| 10 | TestDuplicateWorkerExtended | 2 | 取消/空目录 |

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
