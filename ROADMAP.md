# FileCortex - 路线图 (ROADMAP)

> **版本**: 6.3.3 | **更新日期**: 2026-05-16 | **测试**: 372 passed

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

### v6.3.x 待完成
- [ ] CDN 资源 SRI hash
- [ ] 前端端点集中到 `config.endpoints` (部分完成)
- [ ] BUG-5: Favorites 组选择器选项清理
- [ ] BUG-11: 响应式 CSS grid 冲突
- [ ] HC-2: CSS 魔术值 → CSS 变量 + 亮色主题

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
| **6.3.3** | **2026-05-16** | **8项BUG修复, Google Style整肃, 372 passed, ruff 0 errors, 文档完善** |
| 6.3.2 | 2026-05-14 | 8项BUG修复, DataManager DI, 路由拆分, walk_filtered去重, 路径收集器提取, 348 passed |
| 6.3.1 | 2026-05-10 | 全量架构审计, 10项bug修复, 前后端一致性, 73项新测试, 294 passed |
| 6.3.0 | 2026-04-22 | 内核解耦, WebSocket Auth, Blueprint XML, 221 测试 |
| 6.2.0 | 2026-04-21 | 160 测试, Ruff 0 errors, MCP 完整支持 |
| 6.0.0 | 2026-04-01 | MCP 协议, Categorizer, 蓝图生成 |

---

## 许可证
MIT License
