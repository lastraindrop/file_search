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
- [x] **测试重构 (Resilient Testing)**: 建立了 60+ 矩阵化测试用例，彻底消除环境依赖。

## 📍 阶段 2：高级 AI 编排与多端同步 (短期目标)
- [ ] **ActionBridge 进程管控**: UI 支持手动终止长时脚本运行。
- [ ] **多项目快速切换 UI**: 优化 Web 端 Sidebar 交互。
- [ ] **配置冲突解决机制**: 更好的多端并发修改冲突提示。

## 🚀 长期愿景 (v5.x+)
- [ ] **智能上下文整理 (AI-Driven)**: 引入轻量级 LLM (通过 API 或 本地模型) 对收集到的文件内容进行自动摘要，显著减少发送给对话 AI 的 Token 消耗。
- [ ] **远程服务器编排**: 支持通过 SSH/SFTP 挂载远程目录，实现跨服务器的文件浏览与上下文收集。
- [ ] **插件系统 (UI Hooks)**: 提供开放 API，允许用户定义自定义的文件预览器（如 Jupyter Notebook, CSV 可视化）或编排工具结果渲染插件。

## 🛡️ 架构一致性原则 (Maintenance Principles)
*   **SSOT (Single Source of Truth)**: 所有的路径权限及配置读取必须统一经过 `DataManager` 和 `get_valid_project_root`。
*   **动态对齐 (Dynamic Alignment)**: 任何涉及到路径、Schema 或端到端属性的逻辑，必须在代码和测试中实现动态环境感知，严禁硬编码。
*   **无状态架构**: Web API 必须保持无状态设计，所有上下文通过请求参数传递。
*   **测试驱动**: 核心逻辑的任何变更必须伴随对应的 Pydantic 模型校验更新及 pytest 回归测试。
