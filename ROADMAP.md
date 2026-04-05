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
- [x] **测试重构 (Resilient Testing)**: 建立了 80+ 矩阵化测试用例。
- [x] **测试矩阵补完**: 新增 20+ 个针对安全、资源泄露、路径边界的测试。
- [x] **现代化 Web UI (v5.3 PRO)**: 引入多选、状态反馈、玻璃拟态。
- [x] **快速路径搜集 (v5.3+)**: 实现多端一致的路径格式化搜集。
- [x] **工作区配置管理 (v5.3+)**: 实现置顶项目与 LRU 历史记录。
- [x] **生产加固 (v5.3 Hardening)**: 完成了 72 项测试闭环。

## 📍 阶段 2：通用功能增强与生产加固 (v5.6 - v5.7 增量完成)
- [x] **确定性路径协议 (v5.7)**: 重构了路径归一化，解决了 Windows 驱动器号 Key 漂移 Bug。
- [x] **UI-Backend 引用隔离**: 实现了清单数据的副本机制，杜绝内存引用污染。
- [x] **递归上下文搜集 (v5.7)**: 支持文件夹自动穿透读取与全局去重。
- [x] **标签化多重检索 (v5.5)**: 引入了 positive/negative 标签系统。
- [x] **极速查重工具**: 引入 `DuplicateWorker`（大小预筛 + SHA256）。
- [x] **批量正则重命名 (Regex Rename)**: 实现了基于规则的物理文件批量更名。
- [x] **增强文件预览 (v5.7)**: 支持 Markdown、Mermaid 及超大文本编码识别。

## 📍 阶段 2.8：UX 增强与工业级稳定性 (v5.8 - 当前完成)
- [x] **[DONE] 环境变量注入防御**: ActionBridge 实现了针对 Windows `%` 符号的强制注入审计。
- [x] **[DONE] 强化并发原子锁**: DataManager 实现了方法级 RLock 全流程保护，杜绝字典变动 RuntimeError。
- [x] **[DONE] 路径搜集预设 (Profiles)**: 引入搜集符号预设库（GPT/RAG 模式），支持全端一键切换。
- [x] **[DONE] 非侵入式状态流**: 桌面端实现 Status Stream 机制，告别干扰工作流的 Messagebox。
- [x] **[DONE] 清单智能过滤器**: 实现了 Staging List 的实时动态过滤与批量清理。
- [x] **[DONE] 预览区关键词搜索**: 桌面端支持 `Ctrl+F` 预览内容检索。
- [x] **[DONE] Windows 测试沙箱化**: 彻底解决了 Windows `PermissionError`，实现了残留进程递归杀伤。
- [x] **[DONE] 动态参数对齐 (v5.8)**: 确保了路径搜集符号、过滤器状态在跨端通信中的镜像对称。

## 📍 阶段 3：多端协作与 RAG 准备 (2026 Q3+ 目标)
- [ ] **多模态结构搜集 (Omni-Gatherer)**: 支持 PDF/Excel/Word 语义碎片化抓取。
- [ ] **结构化导出 (RAG-Ready)**: 支持将搜集内容一键打包为 JSONL 或专为 RAG 优化的 Embedding 包。
- [ ] **本地智能摘要 (Semantic Compressor)**: 集成本地模型 (Ollama) 对长代码进行摘要压榨。
- [ ] **多端编排扩展**: 支持通过 SSH/SFTP 编排远程容器内容。

## 🚀 长期愿景 (v6.0+ Agentic Era)
- [ ] **MCP 协议标准化**: 将 FileCortex 核心封装为 MCP 插件，使 AI Agent 能原生调用编排。
- [ ] **自愈型工作流**: 实现 Agent 驱动的本地工程自动化维护（修复 Bug、生成文档）。
- [ ] **跨平台语义文件系统**: 建立索引层，支持基于含义而非路径的检索。

## 🛡️ 架构一致性原则 (Maintenance Principles)
*   **SSOT (Single Source of Truth)**: 所有的路径权限及配置读取必须统一经过 `DataManager`。
*   **动态对齐 (Dynamic Alignment)**: 任何涉及到路径、Schema 或端到端属性的逻辑，必须实现动态环境感知。
*   **测试驱动**: 核心逻辑的任何变更必须伴随对应的 Pydantic 模型校验更新及 pytest 回归测试。
*   **安全分发**: 所有的物理 I/O 操作必须经过 `PathValidator.is_safe` 熔断拦截。
