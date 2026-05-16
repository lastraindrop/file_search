# FileCortex v6.3.2 → v6.3.3 综合审计、BUG修复与完善计划

> **审计日期**: 2026-05-16 | **基线版本**: 6.3.2 | **目标版本**: 6.3.3
> **基线测试**: 348 passed → **目标测试**: 372 passed | **ruff**: 0 errors

---

## A. 系统架构总览

### A.1 分层模型 (4层)

```
┌───────────────────────────────────────────────────────────────┐
│  Entry Points (4)                                              │
│  ┌─────────┐ ┌──────────────┐ ┌──────┐ ┌─────────────────┐    │
│  │ Desktop │ │ Web (FastAPI) │ │ CLI  │ │ MCP Server      │    │
│  │1832行   │ │ REST + WS     │ │135行 │ │ FastMCP       │    │
│  │tkinter  │ │ 127行         │ │argparse│ │ 318行         │    │
│  └────┬────┘ └──────┬───────┘ └──┬───┘ └───────┬─────────┘    │
├───────┴──────────────┴────────────┴──────────────┴────────────┤
│  Route Layer (routers/ 7 modules, ~1200行)                     │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────┐        │
│  │project_routes│ │ fs_routes    │ │ action_routes    │        │
│  │184行         │ │ 327行        │ │ 278行            │        │
│  └──────┬───────┘ └──────┬───────┘ └────────┬─────────┘        │
│         └────────────────┼─────────────────┘                  │
│                   http_routes.py (27行, 合并层)                 │
│                   ws_routes.py (227行)                          │
│                   schemas.py (212行)                            │
│                   services.py (108行)                           │
├───────────────────────────────────────────────────────────────┤
│  Core Kernel (file_cortex_core/ 10 modules, ~2800行)           │
│  ┌─────────┐ ┌──────────┐ ┌─────────┐ ┌────────────────┐      │
│  │ config  │ │ security │ │ search  │ │ context        │      │
│  │596行    │ │ 204行    │ │ 376行   │ │ 203行          │      │
│  │SSOT     │ │沙盒      │ │策略引擎 │ │ LLM格式化     │      │
│  └─────────┘ └──────────┘ └─────────┘ └────────────────┘      │
│  ┌─────────┐ ┌──────────┐ ┌─────────┐ ┌────────────────┐      │
│  │ file_io │ │ actions  │ │ format  │ │ duplicate      │      │
│  │523行    │ │ 572行    │ │ 130行   │ │ 131行          │      │
│  │遍历     │ │文件操作  │ │格式化   │ │ SHA256查重    │      │
│  └─────────┘ └──────────┘ └─────────┘ └────────────────┘      │
│  ┌──────────────────────────────────────────────┐              │
│  │ gui/ (3 modules, ~621行)                     │              │
│  │ PathCollectionDialog + BatchRename + DuplicateFinder     │    │
│  └──────────────────────────────────────────────┘              │
└───────────────────────────────────────────────────────────────┘
```

### A.2 架构评分矩阵

| 维度 | 评分 | 亮点 | 改进空间 |
|------|------|------|----------|
| **SOLID 单一职责** | 8/10 | 路由按域拆分, 内核模块清晰 | `file_search.py` 1832行过大 |
| **SOLID 开闭原则** | 7/10 | 策略模式搜索 (`PathMatcher`/`ContentMatcher`) | 导出格式硬编码 |
| **SOLID 依赖倒置** | 8/10 | DataManager DI (singleton/create/reset/activate) | `get_dm()` 路由注入偏简单 |
| **SOLID 接口隔离** | 7/10 | 路由按功能域拆分 | 部分端点混合 path/deprecated API |
| **DRY** | 9/10 | `walk_filtered()` 统一4处重复遍历 | `flatten_paths` 仍有独立 os.walk |
| **KISS** | 8/10 | 大多数模块清晰可读 | `_prepare_execution` 多平台分支复杂 |
| **安全性** | 9/10 | UNC/Shell注入/目录遍历/Token认证 | CORS origins 比较脆弱 |

### A.3 核心设计原则对齐

| 原则 | 实现 | 位置 | 状态 |
|------|------|------|------|
| SSOT | `DataManager` Pydantic V2 驱动 | `config.py` | ✅ |
| 路径归一化 | `PathValidator.norm_path()` | `security.py` | ✅ |
| 防御深度 | HTTP + WebSocket 双通道 Token | `web_app.py`, `ws_routes.py` | ✅ |
| 遍历共享 | `FileUtils.walk_filtered()` | `file_io.py` | ✅ |
| 原子写入 | tempfile + os.replace + retry | `config.py` | ✅ |
| 策略解耦 | `PathMatcher` + `ContentMatcher` | `search.py` | ✅ |
| 可选导入 | `try/except ImportError` GUI | `__init__.py` | ✅ |

---

## B. 完整 BUG 清单

### BUG-1: `routers/fs_routes.py:81-83` — 截断标志逻辑错误 (中危)

**位置**: `routers/fs_routes.py:81-83`

```python
"is_truncated": len(content.encode("utf-8", errors="ignore")) >= max_preview,
```

**问题**: 当文件字节数恰好等于 `max_preview` 时，`>=` 会错误地报告截断。实际并未截断（恰好读满）。

**修复**: 将 `>=` 改为 `>`。

**影响文件**:
- `routers/fs_routes.py:83`

---

### BUG-2: `file_cortex_core/context.py:175` — CDATA 转义需要循环替换 (中危)

**位置**: `file_cortex_core/context.py:174`

```python
safe_content = content.replace("]]>", "]]]]><![CDATA[>")
```

**问题**: 对于内容 `]]>]]>`，单次 `replace` 后变为 `]]]]><![CDATA[>]]>`，其中产生了新的 `]]>`。因为替换引入的 `]]>` 中的最后部分与原内容中的 `]]>` 结合形成新实例。正确做法需要循环替换直到无变化。

**修复**: 使用循环替换直到稳定。

**影响文件**:
- `file_cortex_core/context.py:174`

---

### BUG-3: `web_app.py:57-59` — CORS origins 比较脆弱性 (中危)

**位置**: `web_app.py:57`

```python
if ALLOWED_ORIGINS != ["*"] and origin not in ALLOWED_ORIGINS:
```

**问题**: 直接列表比较 `["*"]` 在其他代码路径可能被修改。将 `"*"` 作为通配符处理更健壮。

**修复**: 提取为函数，使用 `"*" in ALLOWED_ORIGINS` 检测。

**影响文件**:
- `web_app.py:31-38, 40, 57, 73`

---

### BUG-4: `file_cortex_core/context.py:24` — NoiseReducer.clean 类型标注不准确 (低危)

**位置**: `file_cortex_core/context.py:24`

```python
def clean(content: str, max_line_length: int = 500) -> str:
    ...
    if content is None:
        return ""
```

**问题**: 参数类型标注为 `str`，但函数内处理 `None`。应使用 `Optional[str]`。

**修复**: 将类型标注改为 `str | None`。

**影响文件**:
- `file_cortex_core/context.py:14`

---

### BUG-5: `README.md` 引用不存在的文档 (低危)

**位置**: `README.md:47-48`

```markdown
- [分析报告](ANALYSIS_REPORT.md)
- [前端深度分析](FRONTEND_ANALYSIS.md)
```

**问题**: 这两个文件不存在，造成失效链接。

**修复**: 创建基线文档或移除引用。

**影响文件**:
- `README.md:47-48`
- (新建) `ANALYSIS_REPORT.md`
- (新建) `FRONTEND_ANALYSIS.md`

---

### BUG-6: `file_search.py:1677-1683` — BatchRenameWindow 空值防御 (低危)

**位置**: `file_search.py:1678`

```python
BatchRenameWindow(self.root, self.current_dir, paths, ...)
```

**问题**: 虽在 GUI 环境下 `BatchRenameWindow` 不会为 `None`，但缺少防御性检查。

**修复**: 添加 `if BatchRenameWindow is None: return` 的防御检查。

**影响文件**:
- `file_search.py:1678`

---

### BUG-7 (新发现): `routers/action_routes.py:119` — `dm.data.get()` deprecated API (低危)

**位置**: `routers/action_routes.py:119`

```python
return dm.data.get("global_settings", {})
```

**问题**: 使用 `dm.data` (DEPRECATED 字典视图) 而非 `dm.config.global_settings` (Pydantic 模型)。根据 DEVELOPER_GUIDE 规范应使用后者。

**修复**: 使用 `dm.config.global_settings.model_dump()`。

**影响文件**:
- `routers/action_routes.py:119`

---

### BUG-8 (新发现): `routers/services.py:89` — 相对路径计算可能异常 (低危)

**位置**: `routers/services.py:89`

```python
norm_root = PathValidator.norm_path(project_root_path)
...
norm_entry = PathValidator.norm_path(entry.path)
if norm_entry.startswith(norm_root.rstrip("/") + "/"):
    rel = pathlib.Path(norm_entry[len(norm_root) :].lstrip("/"))
```

**问题**: 当 `norm_entry == norm_root` 时，`startswith` 检查会失败 (因为添加了 `/` 后缀)，然后 `continue`。这是预期行为。但如果路径格式异常，可能产生错误切片。

**修复**: 添加长度保护检查。

**影响文件**:
- `routers/services.py:85-98`

---

## C. 现阶段执行计划 (v6.3.3)

### C.1 立即修复 (本次会话)

| 序号 | 任务 | 文件 | 预估行数 |
|------|------|------|----------|
| 1 | BUG-1: is_truncated >= → > | `routers/fs_routes.py:83` | 1 |
| 2 | BUG-2: CDATA 循环替换 | `file_cortex_core/context.py:174` | 3 |
| 3 | BUG-3: CORS 脆弱性 | `web_app.py:31-38,57,73` | 8 |
| 4 | BUG-4: None 类型标注 | `file_cortex_core/context.py:14` | 2 |
| 5 | BUG-5: 创建缺失文档 | `ANALYSIS_REPORT.md`, `FRONTEND_ANALYSIS.md`, `README.md` | ~100 |
| 6 | BUG-6: GUI None 防御 | `file_search.py:1677-1683` | 3 |
| 7 | BUG-7: deprecated API 替换 | `routers/action_routes.py:119` | 1 |
| 8 | BUG-8: 路径切片保护 | `routers/services.py:89` | 2 |

### C.2 新增测试覆盖

| 测试 | 覆盖内容 | 文件 |
|------|----------|------|
| `test_is_truncated_boundary` | BUG-1: 等于/小于/大于边界 | `test_bugfix_v633.py` (新建) |
| `test_cdata_looping_escape` | BUG-2: 连续 `]]>` 场景 | `test_bugfix_v633.py` |
| `test_cors_origin_wildcard_detection` | BUG-3: origin 比较 | `test_bugfix_v633.py` |
| `test_noise_reducer_none_input` | BUG-4: None 输入 | `test_bugfix_v633.py` |
| `test_global_settings_uses_pydantic_model` | BUG-7: 确认使用模型 | `test_bugfix_v633.py` |
| `test_content_preview_truncation` | 截断标志端到端 | `test_bugfix_v633.py` |

### C.3 验证清单

- [ ] `python -m ruff check .` — 0 errors
- [ ] `python -m pytest tests/ -v` — 全部通过 (372 passed)
- [ ] 所有 BUG 修复点通过新增测试
- [ ] CDN 资源链接可访问 (index.html)

### C.4 版本升级

| 文件 | 旧值 | 新值 |
|------|------|------|
| `file_cortex_core/__init__.py:3` | `"6.3.2"` | `"6.3.3"` |
| `pyproject.toml:7` | `"6.3.2"` | `"6.3.3"` |

---

## D. 未来路线图建议

### D.1 短期 (v6.4, 1-2周)
- [ ] 前端亮色主题 (CSS 变量)
- [ ] API Rate Limiting 中间件
- [ ] `flatten_paths` 归并到 `walk_filtered` 以彻底消除重复遍历
- [ ] 前端虚拟滚动 (万级文件树)

### D.2 中期 (v7.0, 1-2月)
- [ ] 语义搜索 (向量嵌入 + 快速指纹)
- [ ] 插件系统 (Hook 接口)
- [ ] `mypy` 100% 静态类型覆盖
- [ ] Playwright E2E 测试

### D.3 长期 (v8.0+)
- [ ] 本地 LLM 集成 (Ollama)
- [ ] Agent 驱动工作流
- [ ] 云同步配置

---

## E. 技术债务跟踪

| 编号 | 描述 | 优先级 | 状态 |
|------|------|--------|------|
| TD-1 | `file_search.py` 1832行需拆分为多模块 | 中 | 未开始 |
| TD-2 | `flatten_paths` 与 `walk_filtered` 存在功能重叠 | 低 | 未开始 |
| TD-3 | CDN 资源无 SRI hash | 中 | 待完成 |
| TD-4 | CSS 魔术值 → CSS 变量 | 低 | 待完成 |
| TD-5 | 前端 BUG-5: Favorites 组选择器选项清理 | 低 | 待完成 |
| TD-6 | 前端 BUG-11: 响应式 CSS grid 冲突 | 低 | 待完成 |

---

> *本文档为 FileCortex v6.3.2 → v6.3.3 的完整审计结果与执行计划。*
> *所有修复均已映射到具体文件、行号和测试项。*
