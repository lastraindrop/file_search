# AI Context Workbench - 路线图 (ROADMAP)

本文档规划了项目的短期改进目标与长期愿景，旨在保持架构一致性与功能前瞻性。

## 📍 阶段 0：核心巩固与安全加固 (当前状态 - 已完成)
*   **[DONE] 安全架构重构**: 引入了 `PathValidator` 路径组件精准匹配及 Web 端 XSS 防护机制，严防路径穿越与脚本注入。
*   **[DONE] 并发搜索引擎**: 引入 `ThreadPoolExecutor` 并发扫描及 Tkinter UI 批次渲染，彻底解决了大规模项目下的界面卡死。
*   **[DONE] Schema 自动对齐与持久化**: `DataManager` 支持配置字段热补全，并实现了待处理清单 (Staging) 及 收藏夹 (Favorites) 的自动存取。
*   **[DONE] 无状态架构升级**: Web API 移除全局状态依赖，支持浏览器多标签页独立操作不同项目，提升了系统的健壮性。
*   **[DONE] 单元测试革命**: 实现了 **44** 个覆盖核心逻辑、并发压力、安全及 E2E 的测试用例。

## 📅 短期计划 (v4.x - 持续优化)
- [ ] **多项目快速切换 UI**: 优化 Web 端 Sidebar，支持点击项目图标快速载入不同项目，并保持其独立的 Staging 状态。
- [ ] **桌面端解耦重构**: 引入轻量级接口层，将 Tkinter UI 与 `FileOps` 进一步解耦，支持更复杂的批量操作逻辑。
- [ ] **前端虚拟列表**: 对 Web 端文件树进行性能优化，支持在万级节点下保持极速滚动。
- [ ] **增强搜索建议**: 引入搜索历史及基于当前项目语境的路径自动补全。

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
