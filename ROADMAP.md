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

## 📍 阶段 1：编排增强与前端优化 (短期目标)
- [ ] **多项目快速切换 UI**: 优化 Web 端 Sidebar，支持点击项目图标快速载入不同项目。
- [ ] **智能分类规则界面**: 在 Web/Desktop 提供 UI 界面直接配置 `tool_rules`（正则模式与工具关联）。
- [ ] **ActionBridge 进程管控**: 支持在 UI 界面手动终止正在运行的长时脚本（如 `Kill Process`）。
- [ ] **前端虚拟列表**: 对 Web 端文件树进行性能优化，支持在万级节点下保持极速滚动。
- [ ] **配置冲突解决机制**: 针对多端/多标签页并发修改同一项目配置时，提供更好的 UI 级冲突提示。
- [ ] **实时统计仪表盘**: 在侧边栏增加工作区文件总量、Token 预估及分类占比的动态可视化。

## 🚀 长期愿景 (v5.x+)
- [ ] **智能上下文整理 (AI-Driven)**: 引入轻量级 LLM (通过 API 或 本地) 对收集到的文件内容进行自动摘要，减少发送给 AI 的 Token 数量。
- [ ] **Advanced AI Summarization**: 深度集成LLM，实现多文件、跨项目的智能内容关联与摘要生成。
- [ ] **远程服务器连接**: 支持通过 SSH 挂载远程目录，进行跨服务器的上下文收集。
- [ ] **WebDAV/SFTP support**: 增加对WebDAV和SFTP协议的支持，实现更广泛的远程文件系统集成。
- [ ] **插件系统**: 提供开放 API，允许用户自定义文件预览器（例如支持 Jupyter Notebook, CSV 可视化等）。

## 🛡️ 架构一致性原则 (Maintenance Principles)
*   **SSOT (Single Source of Truth)**: 所有的路径权限及配置读取必须统一经过 `DataManager` 和 `get_valid_project_root`。
*   **Stateless API**: 新增的 Web 接口必须保持无状态设计，所有上下文通过请求参数明确传递。
*   **动态对齐**: 必须维护 `DataManager.DEFAULT_SCHEMA` 的唯一性，确保任何配置变更都能触发旧数据的故障自愈。
*   **测试前置**: 核心逻辑的任何变更必须伴随对应的 Pydantic 模型校验更新及 pytest 回归测试。
