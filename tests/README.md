# FileCortex 测试说明

> **测试数**: 661 | **状态**: All Passed | **Ruff**: 0 errors | **版本**: 6.5.1

本项目包含 **661** 项核心全自动化的 `pytest` 测试，采用 **领域驱动深度加固 (Domain-Driven Hardening)** 架构，实现了从底层 IO 到上层 API 契约、前端契约、CLI 与 MCP 的全方位覆盖。

## 测试分层架构

| 层次 | 模块/文件 | 测试数 | 覆盖范围 |
|------|-----------|--------|----------|
| **v6.5.0 全量回归** | `test_v8_comprehensive.py` | 90 | DI/DI反转/OOM保护/CLI search+export/ProcessManager/完整回归 |
| **v6.5.0 安全修复** | `test_security_fixes_v650.py` | 38 | 符号链接遍历/访问控制/MCP安全/线程安全/ProcessManager/死代码消除 |
| **v6.5.0 前端契约** | `test_frontend_contract.py` | 31 | HTML结构/JS模块/CSS/前端功能契约 |
| **v6.5.0 Web API (合并)** | `test_web_api.py` | 42 | CRUD/CORS/Auth/设置/WebSocket/文件操作/安全/端点契约 |
| **v6.4.0 BUG修复** | `test_bugfix_v7.py` | 90 | BUG修复/GlobalSettings/PathValidator/DI/格式工具/搜索 |
| **v6.3.3 BUG修复** | `test_bugfix_v633.py` | 22 | is_truncated/CDATA/CORS/NoiseReducer/version |
| **v6.3.2 回归** | `test_bugfix_v632.py` | 54 | CLI分支/配置API/搜索/路径/文件/噪声/DI |
| **全量回归** | `test_comprehensive_v63.py` | 73 | CLI/MCP/Web/安全/参数对齐/前端契约/弃用API迁移 |
| **核心引擎** | `test_comprehensive.py` | 46 | 核心功能 + 高级边界 |
| **搜索引擎** | `test_search_engine.py` | 20 | 搜索矩阵 (4 mode × 2 params) |
| **安全沙盒** | `test_security_resilience.py` | 23 | 路径验证器全矩阵 (15 场景) |
| **文件操作** | `test_fileops_advanced.py` | 9 | 文件操作完整覆盖 |
| **配置管理** | `test_dm_config.py` | 7 | DataManager 持久化/并发 |
| **集成** | `test_core_integration.py` + `test_scenarios.py` + `test_ai_enhanced.py` | 20 | 编码回弹/级联回滚/完整流程/路径收集 |
| **上下文/MCP** | `test_context_formatter.py` + `test_mcp_server.py` | 9 | XML/MD 导出/MCP 协议 |
| **格式化** | `test_utils_format.py` | 8 | 格式化/Token估算 |
| **边缘覆盖** | `test_additional_coverage.py` + `test_coverage_fill.py` | 47 | 边缘覆盖/ProcessManager/ActionBridge |
| **v6.5.1 P0/P1** | `test_packaging.py` + `test_security_v9.py` | 32 | 打包完整性/安全回归 |
| **总计** | **23 文件** | **661** | **100% 关键路径** |

## 参数对齐测试矩阵

| 参数 | 前端定义 | 后端模型 | 验证测试 |
|------|----------|----------|----------|
| `token_threshold` | `state.js` | `GlobalSettings.token_threshold` (动态默认值) | `test_global_settings_handles_settings_alias` |
| `preview_limit_mb` | `main.js` | `GlobalSettings.preview_limit_mb` (动态默认值) | `test_global_settings_roundtrip` |
| `allowed_extensions` | `main.js` | `GlobalSettings.allowed_extensions` | `test_global_settings_handles_allowed_extensions` |
| `api_token` | `window.__FCTX_API_TOKEN__` | env `FCTX_API_TOKEN` | `test_api_token_header_forward` |
| Version | `{{ version }}` | `__version__` = dynamic | `test_api_index_page_injects_version` |

> **注意**: 所有默认值现在都是动态的——测试使用 `GlobalSettings()` 实例和 `__version__` 而非硬编码的数值，以防止默认值改变时测试失效。

## 运行指令

```bash
# 全量测试
python -m pytest

# 按测试文件
python -m pytest tests/test_comprehensive_v63.py

# 按标记执行
python -m pytest tests/ -m "not slow"
```

## 测试架构原则

1. **隔离性**: 每个测试通过 `_reset_singleton` fixture 获得独立的 `DataManager` 实例
2. **可重现性**: 所有文件操作使用 `tmp_path` fixture 保证临时目录
3. **进程清理**: `conftest.py` 自动清理遗留的 Popen 进程
4. **Windows 兼容**: 测试通过 0.2s 休眠确保文件锁释放
5. **弃用API**: 所有 `dm.data[...]` 已迁移为 `dm.config.xxx` 模型属性
6. **硬编码**: 版本号和默认值使用 `core_version` / `GlobalSettings()` 动态获取
