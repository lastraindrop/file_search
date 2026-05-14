# FileCortex - 路线图 (ROADMAP)

> **版本**: 6.3.2 | **更新日期**: 2026-05-14 | **测试**: 348 passed

---

## 阶段 0-5：核心巩固、架构解耦与深度审计 (已完成)

- [x] **安全架构重构**: PathValidator 路径组件精准匹配及 Web 端 XSS 防护
- [x] **ActionBridge 安全加固**: 跨平台命令执行安全适配
- [x] **并发搜索引擎**: ThreadPoolExecutor 并发扫描及 Tkinter UI 批次渲染
- [x] **Schema 自动对齐与持久化**: DataManager 配置字段热补全
- [x] **LLM 上下文对齐**: XML 导出引擎 (CDATA 封装) + 项目蓝图
- [x] **MCP 协议集成**: mcp_server.py 支持 AI Agent 原生调用
- [x] **内核解耦**: 物理 I/O 与 格式化逻辑彻底分离
- [x] **配置模型化**: Pydantic V2 强类型配置校验 (SSOT)
- [x] **搜索引擎重构**: 匹配策略类抽离，降低复杂度
- [x] **Google 规范**: 全面采纳 Google Style 并通过 ruff 强制执行
- [x] **前端深度分析+修复**: 12 项 BUG 修复、搜索浮层覆盖、API Token 认证修复
- [x] **v6.3.1 全量审计**: 架构分析(SOLID/DRY/KISS) + 10项 bug 修复 + 前后端一致性校验
- [x] **294 项测试基线**: 73 项新增测试，覆盖 CLI/MCP/Web API/安全/文件操作/参数对齐

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
| **6.3.2** | **2026-05-14** | **8项BUG修复, DataManager DI, 路由拆分, walk_filtered去重, 路径收集器提取, 348 passed** |
| 6.3.1 | 2026-05-10 | 全量架构审计, 10项bug修复, 前后端一致性, 73项新测试, 294 passed |
| 6.3.0 | 2026-04-22 | 内核解耦, WebSocket Auth, Blueprint XML, 221 测试 |
| 6.2.0 | 2026-04-21 | 160 测试, Ruff 0 errors, MCP 完整支持 |
| 6.0.0 | 2026-04-01 | MCP 协议, Categorizer, 蓝图生成 |

---

## 许可证
MIT License
