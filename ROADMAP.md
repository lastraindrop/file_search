# FileCortex - 路线图 (ROADMAP)

> **版本**: 6.2.0 | **更新日期**: 2026-04-21 | **测试**: 160 passed

本文档规划了项目的短期改进目标与长期愿景，旨在保持架构一致性与功能前瞻性。

---

## 📍 阶段 0：核心巩固与安全加固 (已完成)
- [x] **安全架构重构**: PathValidator 路径组件精准匹配及 Web 端 XSS 防护机制
- [x] **ActionBridge 安全加固**: 跨平台命令执行安全适配
- [x] **并发搜索引擎**: ThreadPoolExecutor 并发扫描及 Tkinter UI 批次渲染
- [x] **Schema 自动对齐与持久化**: DataManager 配置字段热补全
- [x] **智能分类建议引擎**: 基于文件模式的工具自动推荐
- [x] **无状态架构升级**: Web API 移除全局状态依赖
- [x] **性能压榨**: is_binary Fast-path 及 .gitignore mtime 感知缓存
- [x] **ActionBridge 异步流**: 支持外部工具实时输出捕获
- [x] **批量操作编排**: Web 端全选、批量暂存及批量删除
- [x] **安全校验闭环**: API 权限校验漏洞修复

## 📍 阶段 1：编排增强与前端优化 (已完成)
- [x] **架构解耦**: 从单文件到包结构的平滑迁移
- [x] **AI 特色功能**: Token 计数预估、自动化 Prompt 组装模板
- [x] **现代化 Web UI**: 多选、状态反馈、玻璃拟态
- [x] **工作区配置管理**: 置顶项目与 LRU 历史记录

## 📍 阶段 2：通用功能增强与生产加固 (已完成)
- [x] **确定性路径协议**: 重构路径归一化，解决 Windows 驱动器号 Key 漂移 Bug
- [x] **递归上下文搜集**: 文件夹自动穿透读取与全局去重
- [x] **标签化多重检索**: positive/negative 标签系统
- [x] **极速查重工具**: DuplicateWorker 大小预筛 + SHA256
- [x] **批量正则重命名**: 基于规则的物理文件批量更名
- [x] **增强文件预览**: Markdown、Mermaid 及超大文本编码识别

## 📍 阶段 3：工业级稳定性与 Agentic 增强 (v6.0 - 已完成)
- [x] **分类管理器**: 三栏式文件分类 UI，支持自定义相对路径映射
- [x] **50 项核心精简测试矩阵**: 五大领域驱动模块整合
- [x] **全局统一配置框架**: global_settings 持久化体系
- [x] **LLM 上下文对齐**: XML 导出引擎 (CDATA 封装)
- [x] **项目蓝图**: 一键生成项目架构 ASCII 快照
- [x] **极致 Web UX**: 自定义右键菜单、搜索防抖、全局快捷键
- [x] **MCP 协议集成**: mcp_server.py 支持 AI Agent

## 📍 阶段 4：生产加固与稳定性跃迁 (v6.2.0 - 已完成)
- [x] **160 项全方位回归矩阵**: 格式化边界、噪音消除、Web 安全、前端契约与 GUI 交互回归
- [x] **参数对齐与类型安全**: 二进制单位一致性，类型检查
- [x] **MCP 隔离与独立化**: DataManager 实例化解耦
- [x] **全局规范化一致性**: 路径规范化，消除大小写敏感性 Bug
- [x] **CORS 与日志轮转**: 跨域支持，日志轮转 (10MB, 5备份)
- [x] **MCP 工具扩展**: register_workspace, get_project_blueprint, get_file_stats
- [x] ** Ruff 代码规范**: 157 -> 0 errors
- [x] **Windows 文件句柄优化**: gc.collect() 与 sleep 优化
- [x] **Web 文件树载入修正**: 打开工作区后自动加载首层目录，深层继续懒加载
- [x] **桌面 GUI 清单流修正**: 左侧文件树支持右键直接“添加到清单”
- [x] **历史硬编码清理**: 移除桌面 GUI “发送至图像处理器”，统一为动态 `custom_tools`

## 📍 阶段 5：API 认证与性能监控 (v6.3.0 - 2026 Q3)
- [ ] **[PLANNED] Rate Limiting**: API 端点限流中间件
- [ ] **[PLANNED] SlowAPI 监控**: 记录 >1s 的慢请求
- [ ] **[PLANNED] 异常增强**: 改进异常日志记录
- [ ] **[PLANNED] 全局设置端点收敛**: 合并 `/api/config/global` 与 `/api/global/settings`
- [ ] **[PLANNED] 参数一致性守卫**: 为搜索参数、Token 预算和路径收集参数增加更明确的 schema/契约测试
- [ ] **[PLANNED] GUI/Web 行为对齐**: 清单、收藏、批量操作在桌面端与 Web 端保持同等级可达性

## 📍 阶段 6：架构解耦与插件系统 (v7.0 - 2026 Q4)
- [ ] **[PLANNED] DataManager 重构**: 支持测试隔离，移除全局单例耦合
- [ ] **[PLANNED] 依赖注入**: 移除全局 ACTIVE_PROCESSES 状态
- [ ] **[PLANNED] 插件系统基础**: 定义插件接口，支持自定义工作流
- [ ] **[PLANNED] 路由服务拆分**: 将 `routers/common.py` 继续拆成 `runtime`/`schemas`/`services`
- [ ] **[PLANNED] 前端状态层拆分**: 将 `static/js/app.js` 从单体控制器拆成状态、渲染、动作模块

---

## 🚀 后续愿景 (v8.0+ 智能化编排)

### 长期功能规划
- [ ] **多模态���构搜集**: 支持 PDF/Excel 语义抓取
- [ ] **本地智能摘要**: 集成本地模型 (Ollama) 进行结构化压缩
- [ ] **自愈型工作流**: 实现 Agent 驱动的本地工程自动化维护
- [ ] **语义搜索**: 基于 embedding 的文件相似性搜索
- [ ] **统一交互层**: 桌面 GUI / Web / CLI 共用更稳定的服务层与契约层
- [ ] **可扩展工作流市场**: 基于 `custom_tools` 演化为可发现、可版本化的插件/工作流体系

### 竞品对标
| 特性 | FileCortex | VS Code | Everything | aider |
|-----|-----------|---------|------------|-------|
| 文件搜索 | Multi-mode | Built-in | Instant | - |
| LLM 上下文 | XML/MD+tokens | Extensions | - | Built-in |
| MCP 协议 | Native | Extensions | - | - |
| 文件分类 | Built-in | - | - | - |
| 查重工具 | SHA256 | - | - | fdupes |
| Web UI | Built-in | code-server | - | - |
| 本地优先 | Yes | Yes | Yes | Yes |
| Token 预算 | CJK-weighted | - | - | Basic |

---

## ✅ v6.2 代码规范化验收清单 (2026 Q2 完成)

### 测试验收
- [x] **160 项测试全部通过**: 0 failures
- [x] **测试隔离**: conftest.py 自动清理机制有效
- [x] **Windows 并发**: 无 WinError 5 错误

### 代码质量验收
- [x] **Ruff 零错误**: `ruff check .` 返回 0 errors
- [x] **类型注解**: 所有公共函数完整注解
- [x] **Docstring 规范**: Google 风格文档字符串
- [x] **导入排序**: 标准库 → 第三方 → 本地模块

### 功能验收
- [x] **Web API**: 启动无错误
- [x] **CLI**: fctx open/stage/search 命令正常
- [x] **MCP Server**: stdio 模式启动正常
- [x] **安全性**: PathValidator/ActionBridge 安全检查通过

### 文档验收
- [x] **README.md**: 同步至 v6.2.0
- [x] **DEVELOPER_GUIDE.md**: 扩充至 ~5000 字
- [x] **ROADMAP.md**: 更新阶段 4/5/6
- [x] **ANALYSIS_REPORT.md**: 完整分析报告
- [x] **COMPREHENSIVE_PLAN.md**: 开发计划

---

## 🛡️ 架构一致性原则

### 核心原则
1. **SSOT**: 所有的路径权限及配置读取必须统一经过 DataManager
2. **契约自洽**: API 返回对象必须包含 UI 强依赖字段
3. **逻辑动态对齐**: 禁止硬编码参数，必须从 global_settings 读取
4. **测试驱动**: 核心逻辑变更必须伴随回归测试
5. **安全分发**: 所有物理 I/O 操作必须经过 PathValidator.is_safe

### 代码规范
1. **KISS 原则**: 优先使用内置库解决问题
2. **契约自洽**: 变更 API 前必须更新前端接收逻辑
3. **防御性编程**: 对所有外部输入进行验证
4. **Google Style**: 遵循 Google Python Style Guide

### 维护约定
1. **版本号**: 遵循语义化版本 (Semantic Versioning)
2. **变更日志**: 每次发布必须更新 CHANGELOG
3. **测试覆盖**: 新功能必须包含测试用例
4. **文档同步**: 功能变更必须同步更新文档

---

## 📝 版本历史

| 版本 | 日期 | 重大变更 |
|-----|------|---------|
| 6.2.0 | 2026-04-21 | 160 测试, Ruff 0 errors, MCP 完整支持，Web/GUI 交互补强 |
| 6.1.0 | 2026-04-15 | 80 测试, 全局配置框架, XML 导出 |
| 6.0.0 | 2026-04-01 | MCP 协议, Categorizer, 蓝图生成 |
| 5.8.0 | 2026-03-15 | UNC 拦截, Token 预算, 并发优化 |
| 5.7.0 | 2026-03-01 | 路径归一化, 递归上下文 |

---

## 📝 许可证
MIT License
