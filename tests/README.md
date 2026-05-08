# FileCortex - 自动化测试套件说明 (Test Suite)

> **测试数**: 221 | **状态**: All Passed | **Ruff**: 0 errors

本项目包含 **221** 项核心全自动化的 `pytest` 测试，采用 **领域驱动深度加固 (Domain-Driven Hardening)** 架构，实现了从底层 IO 到上层 API 契约、前端契约与桌面 GUI 动作约束的全方位覆盖。

---

## 📋 测试统计

| 模块 | 测试数 | 覆盖范围 |
|-----|-------|---------|
| test_additional_coverage.py | 30 | 8 个核心模块边缘场景 (Config/FileIO/Search/Format/Context/Actions/Security/Duplicate) |
| test_api_v6.py | 12 | 浏览器契约、生成流程、WebSocket 协议 |
| test_comprehensive.py | 48 | 综合功能、参数边界、跨模块行为 |
| test_context_formatter.py | 6 | XML/MD 导出、Blueprint |
| test_core_integration.py | 11 | 核心集成、编码、查重 |
| test_dm_config.py | 7 | 配置持久化、Schema、并发 |
| test_fileops_advanced.py | 9 | 文件操作、归档、批量 |
| test_frontend_contract.py | 7 | 前端契约、目录树交互、GUI 动作约束 |
| test_mcp_server.py | 3 | MCP 工作区注册、上下文、统计 |
| test_scenarios.py | 2 | 集成场景、参数安全 |
| test_search_engine.py | 20 | 多模式搜索、标签、Gitignore |
| test_security_resilience.py | 23 | 路径安全、注入防护、并发鲁棒性 |
| test_utils_format.py | 8 | 格式化、Token、语言 |
| test_web_api_advanced.py | 21 | API 契约、安全语义、全局设置 |
| test_web_endpoints.py | 9 | 端点边界与工作区行为 |
| test_ai_enhanced.py | 7 | WebSocket 认证、蓝图参数 |
| **总计** | **221** | **100% 关键路径** |

---

## 🧪 新增测试 (`test_additional_coverage.py`)

v6.3.0 新增 30 个测试覆盖 8 个核心模块的边缘场景：

| 测试类 | 方法数 | 测试内容 |
|--------|-------|---------|
| `TestConfigEdgeCases` | 4 | 空输入、类型错误、并发更新、配置回滚 |
| `TestFileIOEdgeCases` | 4 | 空文件编码、超大行、混合编码、符号链接 |
| `TestSearchEdgeCases` | 4 | 空查询、超长查询、空项目、特殊字符 |
| `TestFormatEdgeCases` | 4 | 空路径列表、超大值、无效模式、混合系统路径 |
| `TestContextEdgeCases` | 4 | 空文件列表、大文件、缺失文件、嵌套目录蓝图 |
| `TestActionsEdgeCases` | 4 | 空输入、无效路径、重复目标、只读文件 |
| `TestSecurityEdgeCases` | 3 | 空路径、路径遍历 Unicode 变体、超长路径 |
| `TestDuplicateEdgeCases` | 3 | 空目录、单文件无重复、完整重复流程图 |

---

## 🪟 技术细节 (Technical Guide)

### 核心参数动态对齐

为防止前后端参数不一致导致的 Bug，以下键参数统一通过 `file_cortex_core/__init__.py` 的 `__version__` 和 `state.js` 的 `config` 对象集中管理：

| 参数 | 前端位置 | 后端位置 | 默认值 |
|------|---------|---------|-------|
| **版本号** | `__init__.py:__version__` | `pyproject.toml:version` | `6.3.0` |
| **Token 阈值** | `state.js:config.defaults.tokenThreshold` | `config.py:ProjectConfig.token_threshold` | `100000` |
| **Token 比率** | `state.js:config.defaults.tokenRatio` | `schemas.py:GlobalSettingsRequest.token_ratio` | `4` |
| **搜索排除规则** | `localStorage:searchExcludes` | `config.py:ProjectConfig.excludes` | `.git .idea __pycache__ ...` |
| **API Token** | `window.__FCTX_API_TOKEN__` | `web_app.py:API_TOKEN` | (环境变量 `FCTX_API_TOKEN`) |
| **存档名称** | `state.js:config.defaults.archiveName` | — 纯前端 — | `context_backup.zip` |
| **搜索防抖** | `state.js:config.ui.searchDebounceMs` | — 纯前端 — | `400ms` |
| **侧边栏宽度** | `state.js:config.ui.sidebarWidths` | — 纯前端 — | `collapsed: 60px, expanded: 210px` |

### 测试原则

1. **隔离性**: 使用 `tmp_path` 隔离，全局 `conftest.py` 中的 `on_rmtree_error` 处理 Windows 文件锁
2. **可重复**: 每次运行结果一致，通过 `monkeypatch` 隔离环境变量
3. **清晰性**: 名称描述测试内容
4. **完整性**: 覆盖边界情况（空输入、大值、特殊字符、并发）

### Windows 特殊处理

- `conftest.py` 中的 `clean_config` fixture 使用 `gc.collect()` + `time.sleep(0.05)` 释放文件锁
- `PathValidator.norm_path()` 在 Windows 上自动小写化路径字符串，确保 `assert` 一致性
- 所有 WebSocket 测试使用 `project_client` fixture 自动管理连接生命周期

---

## 🚀 运行测试

### 运行所有测试
```bash
python -m pytest
```

### 运行特定模块
```bash
python -m pytest tests/test_security_resilience.py -v
python -m pytest tests/test_search_engine.py -v
python -m pytest tests/test_web_api_*.py -v
```

### 运行特定测试
```bash
python -m pytest tests/test_security_resilience.py::test_security_path_safe_relative -v
```

### 测试覆盖率
```bash
python -m pytest --cov=file_cortex_core --cov-report=term-missing
```

---

## 🛠 测试开发指南

### 创建新测试
```python
def test_new_feature(mock_project):
    """测试描述"""
    # Arrange
    ...
    # Act
    result = ...
    # Assert
    assert result == expected
```

### 测试 Fixtures (来自 `conftest.py`)
- `clean_config`: 干净的 DataManager 实例 (gc 回收 + 延迟释放文件锁)
- `mock_project`: 包含 src/main.py, README.md, data.bin 的临时项目
- `stress_project`: 深度嵌套的目录结构 (用于蓝图/深度测试)
- `api_client`: FastAPI TestClient (无认证)
- `project_client`: 已打开 `mock_project` 的 FastAPI TestClient

### 测试原则
1. **隔离性**: 使用 `tmp_path` 隔离
2. **可重复**: 每次运行结果一致
3. **清晰性**: 名称描述测试内容
4. **完整性**: 覆盖边界情况

---

## ✅ 验收清单

- [x] 221 tests passed
- [x] 0 failed
- [x] Ruff 0 errors
- [x] Windows 并发通过
- [x] 测试隔离有效

---

## 📝 许可证
MIT License
