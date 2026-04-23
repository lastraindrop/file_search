# FileCortex - 路线图 (ROADMAP)

> **版本**: 6.3.0 | **更新日期**: 2026-04-23 | **测试**: 191 passed

本文档规划了项目的短期改进目标与长期愿景，旨在保持架构一致性与功能前瞻性。

---

## 📍 阶段 0-4：核心巩固、架构解耦与 Agentic 增强 (已完成)
- [x] **安全架构重构**: PathValidator 路径组件精准匹配及 Web 端 XSS 防护机制
- [x] **ActionBridge 安全加固**: 跨平台命令执行安全适配
- [x] **并发搜索引擎**: ThreadPoolExecutor 并发扫描及 Tkinter UI 批次渲染
- [x] **Schema 自动对齐与持久化**: DataManager 配置字段热补全
- [x] **LLM 上下文对齐**: XML 导出引擎 (CDATA 封装) + 项目蓝图集成
- [x] **MCP 协议集成**: mcp_server.py 支持 AI Agent 原生调用
- [x] **191 项回归测试**: 覆盖边界、安全、并发及前端契约

## 📍 阶段 5：外科手术级重构与安全补全 (v6.3.0 - 已完成)
- [x] **内核解耦**: `utils.py` 彻底拆分为 `file_io`, `format_utils`, `context`, `format_utils` 子模块
- [x] **GUI 瘦身**: 抽离大窗口类至 `file_cortex_core.gui`，降低入口文件复杂度
- [x] **WebSocket 安全**: 为搜索流增加基于 `token` 的实时鉴权
- [x] **上下文增强**: XML 导出支持动态注入 `blueprint` (项目蓝图)
- [x] **环境鲁棒性**: 彻底解决 Windows 下的 `WinError 5` 与 `UnicodeDecodeError`
- [x] **前端模块化**: `app.js` 彻底拆分为 ES6 模块 (`state`, `api`, `ui`, `main`)
- [x] **依赖注入 (DI)**: DataManager 全面接入 FastAPI Dependency Injection 模式

## 📍 阶段 6：性能监控与稳定性护航 (Planned - 2026 Q3)
- [ ] **[PLANNED] Rate Limiting**: API 端点限流中间件，防止过度消耗本地资源
- [ ] **[PLANNED] SlowAPI 监控**: 自动记录并导出 >1s 的慢 IO 操作日志
- [x] **参数一致性守卫**: 实现了针对搜索参数、Token 预算的跨端动态 Schema 校验 (v6.3.0)

## 📍 阶段 7：智能化编排与插件生态 (v7.0 - 2026 Q4)
- [ ] **[PLANNED] 插件系统**: 定义标准 Hook 接口，支持用户贡献自定义搜索/导出插件
- [x] **前端状态管理**: `app.js` 拆分为 `state/api/ui/main` 模块，提升 Web 端可维护性 (v6.3.0)
- [ ] **[PLANNED] 多模态支持**: 增加针对 PDF、Excel 等非代码文件的语义抓取

---

## 🚀 后续愿景 (v8.0+ 智能化编排)

### 长期功能规划
- [ ] **本地语义搜索**: 集成轻量级 Embedding 模型，实现基于向量的文件相似性检索
- [ ] **自愈型工作流**: 实现 Agent 驱动的本地工程自动化维护（如自动修复代码规范）
- [ ] **云同步**: 跨设备的安全配置与暂存清单同步

### 竞品对标 (更新)
| 特性 | FileCortex | VS Code | Everything | aider |
|-----|-----------|---------|------------|-------|
| 架构设计 | **微内核 (Microkernel)** | 插件化 | 单体 | 命令行 |
| AI 蓝图 | **Native Blueprint** | 扩展支持 | 无 | 内置 |
| 跨端访问 | **Desktop/Web/CLI/MCP** | GUI/Remote | 仅 GUI | CLI |
| 安全沙盒 | **路径权限注册制** | 基础权限 | 无 | 无 |

---

## ✅ v6.3 代码规范化验收清单 (2026 Q2 完成)

### 测试验收
- [x] **191 项测试全部通过**: 100% 覆盖率
- [x] **测试隔离**: `pytest --basetemp` 机制有效
- [x] **Windows 稳定性**: 解决了编码乱码与物理文件锁冲突

### 代码质量验收
- [x] **Ruff 零错误**: 符合 B904 等高级 lint 规则
- [x] **架构解耦**: 实现物理 IO 与 格式化逻辑的彻底分离
- [x] **UTF-8 标准化**: 确保跨平台 UI 文本无乱码

---

## 🛡️ 架构一致性原则 (2026 修订版)

1. **SSOT (Single Source of Truth)**: 所有的路径权限必须统一经过 `DataManager` 注册，严禁通过硬编码路径进行物理 I/O。
2. **Dynamic Alignment**: 前后端参数（如 Token 比例、搜索模式）必须保持动态对齐，UI 变更必须伴随 API Schema 更新。
3. **Defense-in-Depth**: WebSocket 与 HTTP 共享同等级的安全认证 Token。
4. **Deterministic Normalization**: 所有路径处理必须使用标准的归一化协议，消除大小写与符号链接带来的安全性歧义。

---

## 📝 版本历史

| 版本 | 日期 | 重大变更 |
|-----|------|---------|
| **6.3.0** | **2026-04-22** | **内核解耦, WebSocket Auth, Blueprint XML, 191 测试** |
| 6.2.0 | 2026-04-21 | 160 测试, Ruff 0 errors, MCP 完整支持 |
| 6.0.0 | 2026-04-01 | MCP 协议, Categorizer, 蓝图生成 |

---

## 📝 许可证
MIT License
