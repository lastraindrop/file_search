# FileCortex v6.5.0 — 测试体系优化与规范化计划

## 现状诊断

| 指标 | 数值 |
|------|------|
| 测试文件数 | 22 个 (+ conftest.py) |
| 测试函数数 | 577 个 |
| 测试代码行数 | ~5,200 行 |
| 重复率估计 | ~25-35% |

### 核心问题

1. **大量重复**: `NoiseReducer.clean(None)` 在 5 个文件中重复测试 8 次；`norm_path(None)` 在 5 个文件中重复；`is_safe("", root)` 在 4 个文件中重复
2. **弃用API**: 10+ 处 `dm.data["global_settings"]` 应为 `dm.config.global_settings`
3. **硬编码**: 版本号 "6.5.0" 硬编码在 3 处；默认值 `token_threshold==128000` 硬编码多处
4. **文件膨胀**: `test_bugfix_v632/633/v7` + `test_comprehensive` + `test_comprehensive_v63` + `test_v8_comprehensive` 共 6 个文件声称"全面测试"但严重重叠
5. **覆盖不均**: config/search/context 严重过度覆盖，process_utils/gui/routers 覆盖极薄

---

## Phase A: 弃用API修复 (dm.data → dm.config)

### A-1: test_dm_config.py
| 行号 | 旧代码 | 新代码 |
|------|--------|--------|
| L20-21 | `dm.data["global_settings"]`, `dm.data["projects"]` | `dm.config.global_settings`, `dm.config.projects` |
| L44 | `dm_new.config_path = dm.config_path` | 使用 `patch` |
| L69 | `dm.data["projects"]` | `dm.config.projects` |
| L117 | `dm.data["recent_projects"]` | `dm.config.recent_projects` |
| L122 | `dm.data["global_settings"]["preview_limit_mb"]` | `dm.config.global_settings.preview_limit_mb` |

### A-2: test_comprehensive.py
| 行号 | 旧代码 | 新代码 |
|------|--------|--------|
| L107, L111 | `dm.data["pinned_projects"]` | `dm.config.pinned_projects` |
| L40-50 | `dm.data["projects"]` | `dm.config.projects` |

### A-3: test_comprehensive_v63.py
| 行号 | 旧代码 | 新代码 |
|------|--------|--------|
| L592 | `dm.data["global_settings"]` | `dm.config.global_settings` |
| L615 | `dm.data["recent_projects"]` | `dm.config.recent_projects` |
| L627, L630 | `dm.data["pinned_projects"]` | `dm.config.pinned_projects` |

### A-4: test_additional_coverage.py
| 行号 | 旧代码 | 新代码 |
|------|--------|--------|
| L297 | `dm.data["recent_projects"]` | `dm.config.recent_projects` |

---

## Phase B: 重复测试去重与文件合并

### B-1: 合并 bugfix 回归文件
- `test_bugfix_v632.py` (584行)
- `test_bugfix_v633.py` (239行)
- `test_bugfix_v7.py` (743行)
- 目标: 合并去重为 `test_regression.py` (~500行)

### B-2: 解散 test_additional_coverage.py
- 测试分配到: `test_search_engine.py`, `test_security_resilience.py`, `test_utils_format.py`, `test_dm_config.py`
- 仅保留此文件中真正独有的测试

### B-3: 合并 test_fileops_advanced.py → test_comprehensive.py
### B-4: 合并 test_web_api_advanced.py → test_web_endpoints.py

---

## Phase C: 硬编码修复

- 版本号: 全部改用 `from file_cortex_core import __version__`
- 默认值: 全部改用 `GlobalSettings()` 模型默认值
- 容量常数: 从源模块导入或声明为测试常量

---

## Phase D: 缺失覆盖补充

| 模块 | 新增测试 |
|------|---------|
| `process_utils.py` | `TestTerminateProcess` — 平台检测、无效PID、子进程终止 |
| GUI 组件 | 增强 `TestGUIImportSafety` |
| `routers/common.py` | ProcessManager 边界测试 |

---

## 目标

| 指标 | 当前 | 目标 |
|------|------|------|
| 测试文件数 | 22 | 16 |
| 重复测试率 | ~30% | <5% |
| 弃用API使用 | 14处 | 0处 |
| 硬编码版本号 | 3处 | 0处 |
| 测试总数 | 577 | ~530 (去重后) |
| Ruff | 0 | 0 |
| Pytest | 577 pass | 全部 pass |
