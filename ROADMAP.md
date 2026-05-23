# FileCortex - 路线图 (ROADMAP)

> **版本**: 6.4.0 | **更新日期**: 2026-05-24 | **测试**: 479 passed

---

## 阶段 6.4.0：代码整肃与质量规范 (v6.4.0 — 2026-05-24)

### P0：安全与稳定性修复
- [x] **XSS-1**: `marked.parse()` 添加 sanitization 配置，防止 XSS 注入
- [x] **XSS-2**: 所有用户控制 `innerHTML` 添加 `escapeHtml` 包装器
- [x] **XSS-3**: `api.js` 集中化 `_post()` / `_postJson()` 辅助方法，消除分散 fetch 调用
- [x] **WS-1**: WebSocket `JSON.parse` 使用 try/catch 保护，防止无效数据崩溃
- [x] **WS-2**: WebSocket `onerror` 不再静默返回 false success
- [x] **CSS-1**: 添加缺失的 `.pulse-warning` CSS 类，修复 token 警告动画失效

### P1：类型标注与代码整理
- [x] **类型标注**: 14 处裸 `dict`/`list`/`Queue` → 参数化泛型 (`dict[str, Any]` 等)，覆盖 `schemas.py`, `config.py`, `services.py`, `ws_routes.py`, `search.py`, `actions.py`, `path_collection.py` 共 7 个文件
- [x] **模块提取**: `file_cortex_core/process_utils.py` — 跨平台进程终止工具，从 3 处重复实现中提取
- [x] **命名修复**: `self.q` → `self.query`, `self.pm` → `self.path_matcher` in `search.py`
- [x] **类型修复**: `stop_event: object` → `threading.Event | None` in `file_io.py`
- [x] **常量作用域**: `MAX_LOG_SIZE`, `BACKUP_COUNT` 现在在其定义作用域内被正确引用

### P2：CSS 清理与 HTML 可访问性
- [x] **CSS 去重**: 合并重复的 `.summary-bar` 规则
- [x] **CSS 清理**: 移除未使用的 `.staging-item` 和 `.search-result-item:hover`
- [x] **可访问性**: Toast 容器添加 `aria-live="polite"` 属性
- [x] **可访问性**: 项目路径输入框添加 `aria-label` 属性

### 前端增强
- [x] **左面板重构**: Bootstrap 标签页 → 可折叠区域 (collapsible sections)
- [x] **面板加宽**: staging 面板从 `col-md-2` → `col-md-3`
- [x] **标签管理**: 前端 UI 添加/移除标签管理功能
- [x] **文件创建**: 文件创建模态框，支持从 UI 直接创建新文件
- [x] **SRI 哈希**: 所有 CDN 资源 (Bootstrap CSS/JS, highlight.js) 添加 SRI 哈希；marked@12.0.0 和 mermaid@10.9.0 版本锁定
- [x] **UX 改进**: 所有 `confirm()` 调用替换为 `actionModal` 自定义确认框
- [x] **性能**: `syncStagingToBackend` 添加 debounce，减少频繁 API 调用
- [x] **端点集中**: 所有 WebSocket 端点移至 `config.endpoints` in `state.js`，新增 4 个端点 key

### 测试
- [x] **479 passed, 0 failed** (从 372/463 提升至 479)

### 文档
- [x] 移除不存在文件的引用 (`ANALYSIS_REPORT.md`, `FRONTEND_ANALYSIS.md`)
- [x] `COMPREHENSIVE_PLAN.md` → `COMPREHENSIVE_PLAN_V7.md` (重命名)
- [x] 新增 `CODE_QUALITY_PLAN.md` 至文档列表

### 已完成项目标记 (从 v6.3.x 待完成清单)
- [x] CDN 资源 SRI hash
- [x] 前端端点集中到 `config.endpoints`
- [x] HC-2: CSS 魔术值 → CSS 变量 (部分: `.pulse-warning` 添加, 未使用规则移除, 重复规则合并)

---

## 阶段 6.3.3：代码整肃与深度测试 (v6.3.3 — 已完成 2026-05-16)

### BUG 修复 (8项)
- [x] **BUG-1**: `fs_routes.py` is_truncated 改用文件实际 `st_size` 比较
- [x] **BUG-2**: `context.py` CDATA 转义确认正确 (单次替换, 非循环)
- [x] **BUG-3**: `web_app.py` CORS origins 增加 `_is_wildcard_origin()` 函数
- [x] **BUG-4**: `context.py` NoiseReducer.clean 类型标注 `str` → `str | None`
- [x] **BUG-5**: 创建 `ANALYSIS_REPORT.md` + `FRONTEND_ANALYSIS.md` 基线文档
- [x] **BUG-6**: `file_search.py` BatchRenameWindow None 防御检查
- [x] **BUG-7**: `action_routes.py` deprecated `dm.data.get()` → `dm.config.global_settings.model_dump()`
- [x] **BUG-8**: `services.py` 路径切片增加空值保护

### Google Python Style Guide 整肃
- [x] **Docstrings**: 18个模块添加 Google-style 模块 docstring
- [x] **类型标注**: `web_app.py` middleware 完整签名
- [x] **异常处理**: 3处 `raise e` → `raise` (裸重新抛出)
- [x] **性能**: `mcp_server.py` for/append → 列表推导式

### 文档完善
- [x] **COMPREHENSIVE_PLAN.md**: 完整架构分析 (SOLID评分/分层模型/定位对比) + BUG清单 + 执行计划
- [x] **TECHNICAL_GUIDE.md**: 更新测试数量 + 工作原理完整叙述
- [x] **DEVELOPER_GUIDE.md**: 更新版本 + 测试架构
- [x] **README.md**: 更新测试数量 348→372

### 测试
- [x] **新增 24 项测试** `test_bugfix_v633.py`: is_truncated / CDATA / CORS / NoiseReducer / deprecated API / version
- [x] **372 passed, 0 failed**

---

## 阶段 0-6.3.2：已完成 (历史)

### v6.3.x 待完成

---

## 阶段 6：工程化深耕 (v6.3.2 — 已完成 2026-05-14)

- [x] **8项 BUG 修复**: fctx else 分支逻辑 / results_count 初始化 / None 崩溃 / deprecated API 替换 / ruff 配置清理
- [x] **DataManager 依赖注入**: `create()` / `reset()` / `activate()` 三级 DI 支持
- [x] **路由按域拆分**: `http_routes.py` (743行) → `project_routes` + `fs_routes` + `action_routes` (3模块)
- [x] **共享遍历逻辑**: `FileUtils.walk_filtered()` 统一 4 处重复的 os.walk 模式
- [x] **Desktop GUI 提取**: `PathCollectionDialog` 从单体类中提取为独立组件
- [x] **Clipboard 去重**: 4 处 `clipboard_clear/append` 合并为 `_copy_to_clipboard`
- [x] **GUI 可选导入**: 核心包 `try/except ImportError` 支持 headless 环境
- [x] **348 项测试基线**: 新增 54 项测试，覆盖全链路回归

---

## 阶段 7：智能化编排与插件生态 (v7.0 - 2026 Q4)

- [ ] **[PLANNED] 前端亮色主题**: 通过 CSS 变量实现亮色/暗色主题切换
- [ ] **[PLANNED] 静态类型分析**: 集成 `mypy` 实现 100% 静态类型覆盖
- [ ] **[PLANNED] 拖拽支持**: 实现文件拖拽到 Staging 面板
- [ ] **[PLANNED] Rate Limiting**: API 端点限流中间件
- [ ] **[PLANNED] Virtual Scroll**: Web 端引入虚拟滚动，支持万级文件树
- [ ] **[PLANNED] 前端 E2E 测试**: Playwright/Cypress
- [ ] **[PLANNED] 语义指纹**: 为文件生成快速哈希指纹，加速增量索引
- [ ] **[PLANNED] 插件系统**: 定义标准 Hook 接口，支持自定义搜索/导出插件
- [ ] **[PLANNED] 语义搜索**: 集成轻量级 Embedding 模型，实现向量相似性检索

---

## 后续愿景 (v8.0+)

- [ ] 本地 LLM 集成 (Ollama/llama.cpp)
- [ ] 自愈型工作流 (Agent 驱动的本地工程自动化)
- [ ] 云同步 (跨设备安全配置与暂存清单同步)

---

## v6.3.2 验收清单

### 测试验收
- [x] **348 项测试全部通过**
- [x] 测试隔离机制有效 (DataManager.reset() + process cleanup)
- [x] Windows 稳定性通过

### 代码质量验收
- [x] **Ruff 零错误**
- [x] 路由层按域拆分完成
- [x] 前后端参数动态对齐 (tokenThreshold/preview_limit_mb/allowed_extensions/api_token/version)

### 安全验收
- [x] PathValidator UNC/敏感目录/嵌套路径 全场景覆盖
- [x] API Token HTTP + WebSocket 双通道验证
- [x] CORS 跨域策略可配置

---

## 版本历史

| 版本 | 日期 | 重大变更 |
|-----|------|---------|
| **6.4.0** | **2026-05-24** | **14类型标注, process_utils提取, 3处XSS修复, api.js集中化, 前端可折叠面板, SRI哈希, tag管理, file创建, actionModal, 479 passed** |
| 6.3.3 | 2026-05-16 | 8项BUG修复, Google Style整肃, 372 passed, ruff 0 errors, 文档完善 |
| 6.3.2 | 2026-05-14 | 8项BUG修复, DataManager DI, 路由拆分, walk_filtered去重, 路径收集器提取, 348 passed |
| 6.3.1 | 2026-05-10 | 全量架构审计, 10项bug修复, 前后端一致性, 73项新测试, 294 passed |
| 6.3.0 | 2026-04-22 | 内核解耦, WebSocket Auth, Blueprint XML, 221 测试 |
| 6.2.0 | 2026-04-21 | 160 测试, Ruff 0 errors, MCP 完整支持 |
| 6.0.0 | 2026-04-01 | MCP 协议, Categorizer, 蓝图生成 |

---

## 许可证
MIT License
