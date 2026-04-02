# FileCortex - 路线图 (ROADMAP)

本文档规划了项目的短期改进目标与长期愿景，旨在保持架构一致性与功能前瞻性。

## 📍 阶段 0：核心巩固与安全加固 (当前状态 - 已完成)
*   **[DONE] 安全架构重构**: 引入了 `PathValidator` 路径组件精准匹配及 Web 端 XSS 防护机制，严防路径穿越与脚本注入。
*   **[DONE] ActionBridge 安全加固 (v5.1)**: 实现了跨平台命令执行安全适配，支持 Windows/Unix 变量自动引用转义，杜绝注入攻击。
*   **[DONE] 并发搜索引擎**: 引入 `ThreadPoolExecutor` 并发扫描及 Tkinter UI 批次渲染，彻底解决了大规模项目下的界面卡死。
*   **[DONE] Schema 自动对齐与持久化**: `DataManager` 支持配置字段热补全（新增 `tool_rules`），并实现了待处理清单 (Staging) 及 收藏夹 (Favorites) 的自动存取。
*   **[DONE] 智能分类建议引擎**: 实现基于文件模式 (`fnmatch`) 的工具自动推荐，提升编排效率。
*   **[DONE] 无状态架构升级**: Web API 移除全局状态依赖，支持浏览器多标签页独立操作不同项目。
*   **[DONE] 性能压榨 (v5.1)**: 引入 `is_binary` Fast-path 及 `.gitignore` mtime 感知缓存，大幅降低磁盘 IO 开销。
*   **[DONE] ActionBridge 异步流 (Streaming Output)**: 内核与 Web WebSocket 接口已支持外部工具实时输出捕获。
*   **[DONE] 批量操作编排 (v5.1)**: 实现了 Web 端的全选、批量加入清单及批量物理删除功能，极大优化了大规模工作区的处理速度。
*   **[DONE] 安全校验闭环 (v5.1)**: 完成了 API 权限校验漏洞修复及前端 XSS 注入防护，消除 P0/P1 级风险。

## 📍 阶段 1：编排增强与前端优化 (已完成)
- [x] **架构解耦 (Modernization)**: 已完成从 `core_logic.py` 到 `file_cortex_core/` 包的平滑迁移。
- [x] **AI 特色功能 (v5.2)**: 引入了 Token 计数预估、自动化 Prompt 组装模板。
- [x] **测试重构 (Resilient Testing)**: 建立了 80+ 矩阵化测试用例，彻底消除环境依赖。
- [x] **测试矩阵补完**: 新增 20+ 个针对安全、资源泄露、路径边界及新 API 的测试用例，确保系统生产级稳定。
- [x] **现代化 Web UI (v5.3 PRO)**:
    - 引入多选 Checkbox、加载状态反馈、玻璃拟态增强。
    - 实现了前端异常统一捕获与 Toast 提示，彻底告别“静默失败”。
- [x] **快速路径搜集 (v5.3+)**: 实现多端一致的自定义路径格式化搜集。
- [x] **工作区配置管理 (v5.3+)**: 实现置顶项目 (Pin) 与 LRU 历史记录，确保每项目配置动态对齐。
- [x] **生产加固 (v5.3 Hardening)**: 完成了 72 项测试闭环、修复了路由冲突、逻辑锁升级为 RLock。

## 📍 阶段 2：通用功能增强与生产加固 (v5.6 - v5.7 增量完成)
- [x] **[DONE] 确定性路径协议 (v5.7)**: 重构了 `PathValidator.norm_path`，统一采用 `os.path.abspath` + 小写化处理，彻底解决了 Windows 下驱动器号大小写及 UNC 路径导致的 Key 漂移 Bug。
- [x] **[DONE] UI-Backend 引用隔离**: 实现了清单数据在 UI 与 DataManager 间的“物理隔离”，通过副本机制 (`list()`, `.copy()`) 杜绝了内存引用污染导致的清单丢失问题。
- [x] **[DONE] 递归上下文搜集 (v5.7)**: 支持清单中文件夹的自动穿透读取，并集成了全局去重逻辑，确保上下文输出无重复且完整。
- [x] **[DONE] 标签化多重检索 (v5.5)**: 引入了 `positive/negative` 标签系统，支持多重 AND/NOT 逻辑与局部正则匹配。
- [x] **[DONE] 极速查重工具**: 引入 `DuplicateWorker`（后台线程），采用“大小预筛 + SHA256 哈希”策略。
- [x] **[DONE] ActionBridge 进程管控**: UI 已支持手动终止长时脚本运行（Kill 信号发送与子进程治理）。
- [x] **[DONE] 批量正则重命名 (Regex Rename)**: 实现了基于规则的物理文件批量更名，提升工程编排效率。
- [x] **[DONE] 增强文件预览 (v5.7)**: 支持 Markdown 实时渲染、Mermaid 渲染及流式超大文本编码自动识别 (`read_text_smart`)。
- [x] **[DONE] 智能上下文清洗 (v5.7)**: 扫描引擎深度集成 `.gitignore` 感知，自动过滤冗余二进制与三方依赖。

## 📍 阶段 2.5：工业级并发与资源回收 (v5.7 - 当前里程碑)
- [x] **[DONE] DataManager 全局原子锁**: 实现了配置 I/O 的全程互斥，彻底解决高并发下的写入损坏。
- [x] **[DONE] 共享线程池优化 (Shared Worker Pool)**: 统一管理搜索与查重任务，极大降低了系统的句柄开销与 CPU 峰值。
- [x] **[DONE] Web I/O 阻塞防御**: 将 FastAPI 所有磁盘密集型路由从 `async def` 切换为标准 `def`，利用多线程池保护事件循环。
- [x] **[DONE] UI 异步统计反馈**: 桌面版统计计算完全脱离主线程，界面在大规模扫描下依然能够丝滑响应。

## 📍 阶段 3：RAG 适配与多端协作 (2026 Q3 目标)
- [ ] **结构化导出 (RAG-Ready)**: 支持将搜集内容一键打包为 JSONL 或专为 RAG 模型优化的 Embedding 数据包。
- [ ] **本地智能摘要 (Ollama)**: 集成本地模型对搜集到的代码/文档进行自动化分片与语义摘要。
- [ ] **多端编排扩展**: 支持通过 SSH/SFTP 实现在本地 FileCortex 中编排远程容器内容。

## 🚀 长期愿景 (v6.0+ Agentic Era)
- [ ] **MCP 协议标准化**: 将 FileCortex 核心封装为 MCP (Model Context Protocol) 插件，使 AI Agent (如 Claude Desktop) 能原生调用物理操作。
- [ ] **自动化工作流 (Agents)**: 定义“搜集-编排-分发”的端到端自动化管道，实现 Agent 驱动的本地工程维护。
- [ ] **多模态全文档解析**: 深度支持 PDF、Word 及表格数据的语义提取与 AI 辅助分析。

## 🛡️ 架构一致性原则 (Maintenance Principles)
*   **SSOT (Single Source of Truth)**: 所有的路径权限及配置读取必须统一经过 `DataManager` 和 `get_valid_project_root`。
*   **动态对齐 (Dynamic Alignment)**: 任何涉及到路径、Schema 或端到端属性的逻辑，必须在代码和测试中实现动态环境感知，严禁硬编码。
*   **无状态架构**: Web API 必须保持无状态设计，所有上下文通过请求参数传递。
*   **测试驱动**: 核心逻辑的任何变更必须伴随对应的 Pydantic 模型校验更新及 pytest 回归测试。
*   **安全分发**: 所有的物理 I/O 操作必须经过 `PathValidator.is_safe` 熔断拦截。
