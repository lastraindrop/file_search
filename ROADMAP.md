# FileCortex - 路线图 (ROADMAP)

本文档规划了项目的短期改进目标与长期愿景，旨在保持架构一致性与功能前瞻性。

## 📍 阶段 0：核心巩固与安全加固 (已完成)
*   **[DONE] 安全架构重构**: 引入了 `PathValidator` 路径组件精准匹配及 Web 端 XSS 防护机制。
*   **[DONE] ActionBridge 安全加固 (v5.1)**: 实现了跨平台命令执行安全适配。
*   **[DONE] 并发搜索引擎**: 引入 `ThreadPoolExecutor` 并发扫描及 Tkinter UI 批次渲染。
*   **[DONE] Schema 自动对齐与持久化**: `DataManager` 支持配置字段热补全。
*   **[DONE] 智能分类建议引擎**: 实现基于文件模式的工具自动推荐。
*   **[DONE] 无状态架构升级**: Web API 移除全局状态依赖。
*   **[DONE] 性能压榨 (v5.1)**: 引入 `is_binary` Fast-path 及 `.gitignore` mtime 感知缓存。
*   **[DONE] ActionBridge 异步流 (Streaming Output)**: 支持外部工具实时输出捕获。
*   **[DONE] 批量操作编排 (v5.1)**: 实现了 Web 端全选、批量暂存及批量删除。
*   **[DONE] 安全校验闭环 (v5.1)**: 完成了 API 权限校验漏洞修复。

## 📍 阶段 1：编排增强与前端优化 (已完成)
- [x] **架构解耦 (Modernization)**: 已完成从单文件到包结构的平滑迁移。
- [x] **AI 特色功能 (v5.2)**: 引入了 Token 计数预估、自动化 Prompt 组装模板。
- [x] **现代化 Web UI (v5.3 PRO)**: 引入多选、状态反馈、玻璃拟态。
- [x] **工作区配置管理 (v5.3+)**: 实现置顶项目与 LRU 历史记录。

## 📍 阶段 2：通用功能增强与生产加固 (已完成)
- [x] **确定性路径协议 (v5.7)**: 重构了路径归一化，解决了 Windows 驱动器号 Key 漂移 Bug。
- [x] **递归上下文搜集 (v5.7)**: 支持文件夹自动穿透读取与全局去重。
- [x] **标签化多重检索 (v5.5)**: 引入了 positive/negative 标签系统。
- [x] **极速查重工具**: 引入 `DuplicateWorker`（大小预筛 + SHA256）。
- [x] **批量正则重命名 (Regex Rename)**: 实现了基于规则的物理文件批量更名。
- [x] **增强文件预览 (v5.7)**: 支持 Markdown、Mermaid 及超大文本编码识别。

## 📍 阶段 3：工业级稳定性与 Agentic 增强 (v6.0 - 2026 Q2 达成) [x]
- [x] **[DONE] 分类管理器 (Categorizer)**: 
    - 实现了三栏式文件分类 UI，支持自定义相对路径映射。
- [x] **[DONE] 236 项全量测试矩阵**: 
    - 覆盖架构适配、参数组合与 API 契约深度校验（修复了 content 模式字段漂移 Bug）。
- [x] **[DONE] 全局统一配置框架 (Unified Settings)**:
    - 引入了 `global_settings` 持久化体系，彻底消除预览上限 (Preview Limit) 的硬编码。
- [x] **[DONE] LLM 上下文对齐 (v6.0 Innovation)**:
    - 实现了 **XML 导出引擎**（CDATA 封装），大幅提升 LLM 对复杂代码片段的解析精度。
    - 引入了 **Project Blueprint (项目蓝图)** 功能，一键生成项目架构 ASCII 快照。
- [x] **[DONE] 极致 Web UX (v6.0 Polish)**:
    - 实现 Web 端自定义右键菜单、搜索防抖 (Debounce) 和全局快捷键辅助。
- [x] **[DONE] MCP 协议集成**: 
    - 创建了 `mcp_server.py`，使 FileCortex 能够作为 Claude Desktop 的插件原生工作。

## 🚀 后续愿景 (v7.0+ 智能化编排)
- [ ] **多模态结构搜集 (Omni-Gatherer)**: 支持 PDF/Excel 语义抓取。
- [ ] **本地智能摘要 (Semantic Compressor)**: 集成本地模型对其长代码进行结构化压缩。
- [ ] **自愈型工作流**: 实现 Agent 驱动的本地工程自动化维护（修复 Bug、生成文档）。

## 🛡️ 架构一致性原则 (Maintenance Principles)
*   **SSOT (Single Source of Truth)**: 所有的路径权限及配置读取必须统一经过 `DataManager`。
*   **契约自洽性 (Contract Cohesion - v6.0 NEW)**: 
    - **API 字段强校验**: 任何提供给前端的 API 对象（特别是搜索结果与文件元数据）**必须** 包含 UI 强依赖字段：`abs_path`, `name`, `size_fmt`, `mtime_fmt`。
    - **逻辑动态对齐**: 类似于预览上限 (1MB) 等参数必须从 `global_settings` 动态读取，禁止在前端或后端代码中出现 `1024*1024` 类的硬编码。
*   **测试驱动**: 核心逻辑变更**必须**伴随 `pytest` 回归测试，尤其是多参数组合 (Parametrize) 探查。
*   **安全分发**: 所有的物理 I/O 操作必须经过 `PathValidator.is_safe` 熔断拦截。
