# FileCortex - 路线图 (ROADMAP)

> **版本**: 6.3.1 | **更新日期**: 2026-05-10 | **测试**: 294 passed

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

## 阶段 6：工程化深耕与性能监控 (Planned - 2026 Q3)

- [ ] **[PLANNED] 静态类型分析**: 集成 `mypy` 实现 100% 静态类型覆盖
- [ ] **[PLANNED] DataManager 依赖注入重构**: 取代 Service Locator 模式
- [ ] **[PLANNED] 前端亮色主题**: 通过 CSS 变量实现亮色/暗色主题切换
- [ ] **[PLANNED] 拖拽支持**: 实现文件拖拽到 Staging 面板
- [ ] **[PLANNED] Rate Limiting**: API 端点限流中间件
- [ ] **[PLANNED] Virtual Scroll**: Web 端引入虚拟滚动，支持万级文件树
- [ ] **[PLANNED] 前端 E2E 测试**: Playwright/Cypress
- [ ] **[PLANNED] Desktop GUI 拆分**: 从 1919行单体类提取 Controller/View

---

## 阶段 7：智能化编排与插件生态 (v7.0 - 2026 Q4)

- [ ] **[PLANNED] 路由拆分**: `http_routes.py` 按功能域拆分为多个路由模块
- [ ] **[PLANNED] 语义指纹**: 为文件生成快速哈希指纹，加速增量索引
- [ ] **[PLANNED] 插件系统**: 定义标准 Hook 接口，支持自定义搜索/导出插件
- [ ] **[PLANNED] 语义搜索**: 集成轻量级 Embedding 模型，实现向量相似性检索

---

## 后续愿景 (v8.0+)

- [ ] 本地 LLM 集成 (Ollama/llama.cpp)
- [ ] 自愈型工作流 (Agent 驱动的本地工程自动化)
- [ ] 云同步 (跨设备安全配置与暂存清单同步)

---

## v6.3.1 验收清单

### 测试验收
- [x] **294 项测试全部通过**
- [x] 测试隔离机制有效 (singleton reset + process cleanup)
- [x] Windows 稳定性通过

### 代码质量验收
- [x] **Ruff 零错误**
- [x] 架构解耦实现
- [x] 前后端参数动态对齐 (tokenThreshold/preview_limit_mb/allowed_extensions/api_token/version)

### 安全验收
- [x] PathValidator UNC/敏感目录/嵌套路径 全场景覆盖
- [x] API Token HTTP + WebSocket 双通道验证
- [x] CORS 跨域策略可配置

---

## 架构一致性原则

1. **SSOT**: 所有路径权限统一经过 `DataManager` 注册，严禁硬编码路径直接 I/O。
2. **Dynamic Alignment**: 前后端参数必须保持动态对齐，UI 变更伴随 API Schema 更新。
3. **Defense-in-Depth**: WebSocket 与 HTTP 共享同等级安全认证 Token。
4. **Deterministic Normalization**: 所有路径处理使用标准归一化协议，消除跨平台歧义。

---

## 版本历史

| 版本 | 日期 | 重大变更 |
|-----|------|---------|
| **6.3.1** | **2026-05-10** | **全量架构审计, 10项bug修复, 前后端一致性, 73项新测试, 294 passed** |
| 6.3.0 | 2026-04-22 | 内核解耦, WebSocket Auth, Blueprint XML, 221 测试 |
| 6.2.0 | 2026-04-21 | 160 测试, Ruff 0 errors, MCP 完整支持 |
| 6.0.0 | 2026-04-01 | MCP 协议, Categorizer, 蓝图生成 |

---

## 许可证
MIT License
