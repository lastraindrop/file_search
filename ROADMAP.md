# FileCortex - 路线图 (ROADMAP)

> **当前版本**: 6.5.1 | **更新日期**: 2026-06-15 | **测试**: 652 passed | **Ruff**: 0 errors | **Google Style**: 全规范审计完成

---

## 阶段 6.5.1：部署加固与安全补强 (v6.5.1 — 2026-06-15)

### 部署阻断修复 (P0)
- [x] **BUG-D1**: `pyproject.toml` 打包缺漏 `routers` 包 → `packages` 补全
- [x] **BUG-D2**: `mcp` SDK 未列入依赖 → 新增 `[mcp]` 可选依赖组 + README 安装说明
- [x] **BUG-Doc5**: 无 `fctx-mcp` 控制台脚本 → `pyproject.toml [project.scripts]` 补全

### 安全修复 (P0)
- [x] **BUG-W2**: `api_categorize` 路径遍历 → 逐项 `is_path_safe` 校验
- [x] **BUG-W1**: API Token 经 index 页泄露 → `_is_local_request` 守卫；`hmac.compare_digest`
- [x] **BUG-F1**: mermaid CDN 缺 SRI → `integrity="sha384-6F4Ibv..."` 补齐

### 安全加固与一致性 (P1)
- [x] **BUG-W7/W9**: 无界输入字段 → 11 个 `list[str]` 加 `max_length=1000`；dict 字段加 `field_validator`
- [x] **BUG-W10**: Token 时序侧信道 → `hmac.compare_digest`
- [x] **BUG-W4**: WS `search_task` 孤儿线程 → `finally` 取消
- [x] **BUG-W5**: ProcessManager PID 复用 → `register` 拒绝活跃重叠
- [x] **BUG-W6**: `api_terminate_process` TOCTOU → 用 Popen 对象终止
- [x] **BUG-W8**: `FileSaveRequest` 缺 `project_path` → 新增 Optional 字段
- [x] **BUG-C1**: `to_xml` 静默吞异常 → 加 `logger.exception`
- [x] **BUG-C2**: `archive_selection` 目录分支 `ValueError` → 逐文件 arcname 决策
- [x] **BUG-C3**: Windows 长路径 `\\?\` 误判 UNC → 剥离后检查
- [x] **BUG-C4**: `batch_rename` `count=1` 未文档化 → 增加 `count` 参数
- [x] **BUG-C5/C6**: search pool shutdown + worker 异常 → submit 检查 + 异常入队
- [x] **BUG-F4**: `ctxAction` 状态污染 → try/finally 恢复

### 测试补强
- [x] `tests/test_packaging.py`: 6 项 (D1/D2/Doc5 回归)
- [x] `tests/test_security_v9.py`: 17 项 (W1/W2/W5/W6/W7/W9/W10/F1 回归)
- [x] **652 passed, 0 failed** (从 629→652，+23 项；文件数 21→23)

---

## 阶段 6.5.0：安全加固、前端优化与测试整合 (v6.5.0 — 2026-06-07)

### 安全修复 (Security Fixes)
- [x] **SEC-1**: `security.py` 符号链接遍历防护 (`Path.resolve()` 解析)
- [x] **SEC-2**: `action_routes.py` `/api/generate` 未注册项目路径 → 403
- [x] **SEC-3**: `config.py` `activate()` 和 `resolve_project_root()` 线程安全 (RLock)
- [x] **SEC-4**: `mcp_server.py` `register_workspace` 统一使用 `validate_project()`
- [x] **SEC-5**: CLI `cmd_open` 统一入口验证

### 前端优化 (Frontend Optimization)
- [x] **FE-8**: Markdown 渲染 XSS 防护 (DOMPurify 3.1.6 + SRI)
- [x] **FE-9**: Ctrl+S 双重保存竞态修复 (`stopPropagation`)
- [x] **FE-10**: 三栏布局修复 (col-md-5→col-md-6, 11/12→12/12)
- [x] **FE-11**: 搜索 snippet 转发 (ws_routes.py + ui.js)
- [x] **FE-12**: 模态框堆叠修复 (toolResultModal + actionModal)
- [x] **FE-13**: 移动端 vh-100 → 100dvh 修复
- [x] **FE-14**: CSS 硬编码颜色统一为变量 (var(--accent)、var(--glass-blur))
- [x] **FE-15**: 侧边栏宽度单一数据源 (移除 HTML 内联样式)
- [x] **FE-16**: `selectedFiles` 项目切换清理、WebSocket onerror 置空、toggleSidebar 缓存

### 后端修复 (Backend Fixes)
- [x] **BUG-6**: `file_io.py` 移除不可达 `return ""`
- [x] **BUG-7**: `action_routes.py` stats 端点内存限制 (`max_bytes=1MB`)
- [x] **BUG-8**: `action_routes.py` ProcessManager 封装 (移除旧全局变量引用)
- [x] **BUG-11**: `fctx.py` CLI `cmd_open` 安全验证

### 测试整合 (Test Consolidation)
- [x] **TC-1**: 6 个完全重复测试去重 (norm_path、clean_*、is_safe_*、collect_paths)
- [x] **TC-2**: Web API 测试合并 (test_web_endpoints + test_web_api_advanced + test_api_v6 → test_web_api.py, 42 tests)
- [x] **TC-3**: 硬编码值动态化 (128000→>0, 1.0→>0, 版本号→__version__)
- [x] **TC-4**: 新增 38 项安全修复测试 (test_security_fixes_v650.py)
- [x] **TC-5**: **629 passed, 0 failed** (从 597→629, +32 项; 文件数 23→21)

### P0：异常日志规范化
- [x] **LOG-1**: 23 处 `logger.error(f"...{e}")` → `logger.exception("...")`，保留栈轨迹
- [x] **LOG-2**: 22 处冗余 `as e` 绑定被 Ruff F841 自动清理

### P1：类型注解补齐
- [x] **TYPE-1**: `build_exe.py` `build()` → `main() -> None`
- [x] **TYPE-2**: `mcp_server.py` 3 处缺失返回值类型 (`tool`, `run`, `get_dm`)
- [x] **TYPE-3**: `file_io.py` `walk_filtered` 生成器返回值 `Generator[...]`
- [x] **TYPE-4**: `config.py` `DataManager.activate()` 返回值 `Generator[...]`
- [x] **TYPE-5**: `gui/path_collection.py` `status_callback` 参数类型
- [x] **TYPE-6**: `gui/batch_rename.py` `callback` 参数类型

### P2：Import 规范化
- [x] **IMP-1**: `mcp_server.py` third-party→local import 顺序修正
- [x] **IMP-2**: `web_app.py` `uvicorn`/`fastapi` 字母序修正
- [x] **IMP-3**: `search.py`/`actions.py`/`file_io.py` stdlib 组字母序修正
- [x] **IMP-4**: `build_exe.py`  import 分组规范化

### P3：线程安全与入口规范化
- [x] **THR-1**: `SearchWorker`/`DuplicateWorker` daemon=True 构造器传参
- [x] **MAIN-1**: `file_search.py` `__main__` → `main()` 函数封装
- [x] **MAIN-2**: `build_exe.py` `__main__` → `main()` 函数封装
- [x] **NME-1**: `mcp_server.py` `format` 参数 → `fmt`（遮蔽修复）

### CLI 增强
- [x] **CLI-1**: `fctx search` 子命令 (smart/exact/regex/content 模式)
- [x] **CLI-2**: `fctx export` 子命令 (markdown/xml, --output 参数)

### OOM 保护
- [x] **OOM-1**: `context.py` 导出限流：`MAX_EXPORT_FILES=500`, `MAX_TOTAL_CONTENT_BYTES=50MB`

### 进程管理封装
- [x] **PM-1**: `routers/common.py` `ProcessManager` 线程安全容器
- [x] **PM-2**: 容量限制 (50个)、旧 API 别名兼容

### 前端修复
- [x] **FE-1**: `stageAll` CRITICAL BUG 修复 (搜索模式字符串→固定 'files')
- [x] **FE-2**: 上下文菜单越界保护 (viewport clip)
- [x] **FE-3**: `bulkActions` 死代码 (display:none→display:flex)
- [x] **FE-4**: `tree-node` 选择器全局污染 (scoped)
- [x] **FE-5**: `noteOverlay` 定位修复
- [x] **FE-6**: `_createKeyValueRow` key 清理
- [x] **FE-7**: `addToFavorites` 防御检查

### 后端回归修复
- [x] **BUG-1**: `file_io.py` `read_text_smart` 返回空字串兜底 (`""`)
- [x] **BUG-2**: `actions.py` `batch_categorize` DataManager DI 支持
- [x] **BUG-3**: `config.py` `MAX_SAVE_RETRIES` 独立常量
- [x] **BUG-4**: `duplicate.py` 空值防御检查
- [x] **BUG-5**: `fctx.py` elif 链修复
- [x] **BUG-6**: `search.py` 线程池优雅关闭 (cancel_futures)

### 弃用 API 迁移
- [x] **DEP-1**: `test_dm_config.py` `dm.data["global_settings"]` → `dm.config.global_settings`
- [x] **DEP-2**: `test_comprehensive.py` `dm.data["pinned_projects"]` → `dm.config.pinned_projects`
- [x] **DEP-3**: `test_comprehensive_v63.py` 4 处 `dm.data[...]` 迁移
- [x] **DEP-4**: `test_additional_coverage.py` `dm.data["recent_projects"]` 迁移

### 硬编码修复
- [x] **HARD-1**: 测试文件版本号 `"6.5.0"` → `core_version` 动态导入
- [x] **HARD-2**: 测试文件默认值 `== 128000` → `GlobalSettings()`

### 测试增强
- [x] **TEST-1**: `test_v8_comprehensive.py` 新增 77 项 (DI/OOM/CLI/ProcessManager)
- [x] **TEST-2**: `test_coverage_fill.py` 新增 20 项 (process_utils/ProcessManager)
- [x] **TEST-3**: `test_frontend_contract.py` 新增 8 项 (前端契约)
- [x] **TEST-4**: **597 passed, 0 failed** (从 479→597，+118 项)

### 文档
- [x] 所有文档版本号同步 6.4.0 → 6.5.0
- [x] `README.md` 死链清理 (COMPREHENSIVE_PLAN_V7.md/CODE_QUALITY_PLAN.md 移除)
- [x] `TECHNICAL_GUIDE.md` v6.5.0 审计结果补充
- [x] `tests/README.md` 测试数 348→597
- [x] `ROADMAP.md` 新增 v6.5.0 完成章节

---

## 阶段 v6.4.0：代码整肃与质量规范 (已完成 2026-05-24)
*(完整内容见 Commit 记录)*

- [x] process_utils 提取, 14 类型标注, 3 处 XSS 修复
- [x] api.js 集中化, 前端可折叠面板, SRI 哈希, tag 管理, file 创建, actionModal
- [x] **479 passed, 0 failed**

---

## 阶段 v6.3.3：代码整肃与深度测试 (已完成 2026-05-16)
*(完整内容见 Commit 记录)*

- [x] 8 项 BUG 修复, Google Style 整肃
- [x] **372 passed, 0 failed**

---

## 阶段 v6.3.2：工程化深耕 (已完成 2026-05-14)
*(完整内容见 Commit 记录)*

- [x] 8 项 BUG 修复, DataManager DI, 路由拆分, walk_filtered 去重
- [x] **348 passed, 0 failed**

---

## 阶段 7：智能化编排与插件生态 (v7.0 — 2026 Q3-Q4)

> **v6.5.1 铺路**: P0/P1 安全加固为 v7.0 演进奠定信任地基（部署可用、认证不泄露、操作不越界）。

### 高优先级 (v7.0 MVP)
- [x] **[DONE v6.5.0] 测试文件合并优化**: 23→21 文件精简，重复率已消除
- [x] **[DONE v6.5.1] 部署加固**: `pip install .` 可用、MCP 依赖声明、分类路径安全
- [x] **[DONE v6.5.1] API Token 安全**: 本地注入/网络不泄露 + `hmac.compare_digest` 常量时间
- [x] **[DONE v6.5.1] 输入校验**: 所有 `list[str]` 字段 `max_length=1000`；dict 字段 size validator
- [ ] **[PLANNED] 静态类型分析**: 集成 `mypy` 实现 100% 静态类型覆盖
- [ ] **[PLANNED] 前端亮色主题**: 通过 CSS 变量实现亮色/暗色主题切换
- [ ] **[PLANNED] 拖拽支持**: 实现文件拖拽到 Staging 面板
- [ ] **[PLANNED] Rate Limiting**: API 端点限流中间件
- [ ] **[PLANNED] 前端 E2E 测试**: Playwright 浏览器端回归

### 中优先级 (v7.0 增强)
- [ ] **[PLANNED] Virtual Scroll**: Web 端引入虚拟滚动，支持万级文件树
- [ ] **[PLANNED] 语义指纹**: 为文件生成快速哈希指纹，加速增量索引
- [ ] **[PLANNED] Tree-sitter 压缩导出**: 保留签名剥离实现体，~70% token 削减（借鉴 Repomix）
- [ ] **[PLANNED] PageRank 上下文优先级**: 智能导出按依赖图排名纳入相关文件（借鉴 Aider）
- [ ] **[PLANNED] 插件系统**: 定义标准 Hook 接口，支持自定义搜索/导出插件
- [ ] **[PLANNED] CSP 落地**: 内联事件处理器 → `addEventListener` 迁移
- [ ] **[PLANNED] CI Windows runner**: `.github/workflows/test.yml` matrix 加 `windows-latest`

### 低优先级
- [ ] **[PLANNED] 语义搜索**: 集成轻量级 Embedding 模型，实现向量相似性检索
- [ ] **[PLANNED] `exec_async` 化**: `api_execute_tool` 同步阻塞→async subprocess，防线程池耗尽

---

## 后续愿景 (v8.0+)

- [ ] 本地 LLM 集成 (Ollama/llama.cpp)
- [ ] 自愈型工作流 (Agent 驱动的本地工程自动化)
- [ ] 云同步 (跨设备安全配置与暂存清单同步)

---

## 版本历史

| 版本 | 日期 | 重大变更 |
|-----|------|---------|
| **6.5.1** | **2026-06-15** | **P0/P1 部署加固: 打包修复+D2 MCP 依赖/categorize 路径遍历修补/token 泄露修复+mermaid SRI; 13 项安全加固 (输入上限/时序/WS task/PID复用/Popen终止/context日志/archive/long-path/rename count/search pool/SearchWorker/ctxAction); +23 新测试; 652 passed** |
| **6.5.0** | **2026-06-07** | **安全加固(11项BUG修复), 前端优化(9项), 测试整合(21→629), 符号链接防护, DOMPurify XSS, 三栏布局修复, 动态参数对齐, 629 passed** |
| **6.5.0-rc1** | **2026-05-29** | **Google Style 全审计, 23 处日志规范化, 118 新测试, CLI search/export, OOM 保护, ProcessManager, 前端 8 项修复, 597 passed** |
| **6.4.0** | **2026-05-24** | **14 类型标注, process_utils 提取, 3 处 XSS 修复, api.js 集中化, 前端可折叠面板, SRI 哈希, tag 管理, file 创建, actionModal, 479 passed** |
| 6.3.3 | 2026-05-16 | 8 项 BUG 修复, Google Style 整肃, 24 新测试, 372 passed |
| 6.3.2 | 2026-05-14 | 8 项 BUG 修复, DataManager DI, 路由拆分, walk_filtered, 348 passed |
| 6.3.1 | 2026-05-10 | 全量审计, 10 BUG 修复, 前后端一致性, 294 passed |
| 6.3.0 | 2026-04-22 | 内核解耦, WebSocket Auth, Blueprint XML, 221 tests |
| 6.2.0 | 2026-04-21 | 160 tests, Ruff 0 errors, MCP 完整支持 |
| 6.0.0 | 2026-04-01 | MCP 协议, Categorizer, 蓝图生成 |

---

## 许可证
MIT License
