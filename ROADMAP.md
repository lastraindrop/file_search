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

## 📍 阶段 3：工业级稳定性与分类控制 (v6.0 - 当前完成) [x]
- [x] **[DONE] 分类管理器 (Categorizer)**: 
    - 实现了三栏式文件分类 UI，支持自定义相对路径映射。
    - 集成后端物理移动逻辑与跨项目安全拦截。
- [x] **[DONE] 226 项回归测试矩阵**: 
    - 测试用例从 183 提升至 226，覆盖率覆盖架构适配、参数组合与 API 契约深度校验。
    - 实现了测试态的 **Active Process Termination**，彻底解决 Windows 文件句柄占用冲突。
- [x] **[DONE] 契约式 API 协议 (v6.0 Contract)**: 
    - 强制 API 返回结构对齐，引入 `size_fmt`, `mtime_fmt`, `is_truncated`, `encoding` 等 UI 级自洽字段。
    - 强制所有 API 进行物理路径规一化，消除前后端路径一致性隐患。
- [x] **[DONE] 工业级生产加固**: 修复了 `os.scandir` 在并发场景下的句柄泄露及 Windows UNC 路径安全漏洞。

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
  - [x] **v6.0 深度契约协议 (Hardened Contract - v6.0)**: 
    - **API 上下文保障**: 任何涉及文件列表统计（如 `StatsRequest`）或内容生成（如 `GenerateRequest`）的模型必须显式包含 `project_path`。**v6.0 统一要求所有配置请求必须过 DataManager 逻辑校验，严禁直接读写内存字典。**
    - **响应式元数据**: `get_node_info` 强制返回 `size_fmt`, `mtime_fmt`, `has_children` 等 UI 就绪映射，避免前端进行逻辑重组。
    - **物理对齐原则**: 搜寻结果 `path` 与 API 入参通过 `PathValidator.norm_path` 实现物理级一致性。
    - **OOM 拦截规约**: 所有的文本读取操作必须调用 `FileUtils.read_text_smart`。**v6.0 引入了 Context 生成单文件 1MB 强制熔断。**
    - **句柄自闭环 (Resource Safety)**: 全部 I/O 扫描逻辑强制封装在 `with os.scandir(...)` 上下文管理器中，解决 Windows 文件锁定难题。
*   **动态对齐 (Dynamic Alignment)**: 任何涉及到路径、Schema 或端到端属性的逻辑，必须实现动态环境感知。
*   **测试驱动**: 核心逻辑的任何变更必须伴随对应的 Pydantic 模型校验更新及 pytest 回归测试。
*   **安全分发**: 所有的物理 I/O 操作必须经过 `PathValidator.is_safe` 熔断拦截。
