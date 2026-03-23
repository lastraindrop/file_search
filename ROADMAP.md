# AI Context Workbench - 路线图 (ROADMAP)

本文档规划了项目的短期改进目标与长期愿景，旨在保持架构一致性与功能前瞻性。

## 📍 阶段 0：核心巩固 (当前状态 - 已完成)
*   **[DONE] 安全架构重构**: 引入了 `get_valid_project_root` 集中权限验证，杜绝路径越权访问。
*   **[DONE] 命令注入修复**: 桌面端 PowerShell 调用完全参数化，规避 RCE 风险。
*   **[DONE] 性能兜底**: `generate_ascii_tree` 引入深度截断 (Depth Limit)，防止死循环。
*   **[DONE] 单元测试革命**: 实现了 35 个全场景覆盖的测试用例，集成 Mock 安全验证。

## 📅 短期计划 (v4.x - 下一阶段)
- [ ] **参数一致性检查 (Dynamic Alignment)**: 在 `DataManager` 中引入参数校验器，确保 Web 端与桌面端配置字段的完全对齐，避免因 UI 表单字段差异导致的 KeyError。
- [ ] **多项目快速切换**: 优化 Web 端 Sidebar，支持点击项目图标直接切换 Project Root，保持 Session 隔离。
- [ ] **异步搜索性能优化**: 在 `core_logic.py` 中引入 `ThreadPoolExecutor` 对文件内容搜索进行并行处理，提升大规模项目搜索效率。

## 🚀 长期愿景 (v5.x+)
- [ ] **智能上下文整理 (AI-Driven)**: 引入轻量级 LLM (通过 API 或 本地) 对收集到的文件内容进行自动摘要，减少发送给 AI 的 Token 数量。
- [ ] **远程服务器连接**: 支持通过 SSH 挂载远程目录，进行跨服务器的上下文收集。
- [ ] **插件系统**: 提供开放 API，允许用户自定义文件预览器（例如支持 Jupyter Notebook, CSV 可视化等）。

## 🛡️ 架构一致性原则 (Maintenance Principles)
*   **SSOT (Single Source of Truth)**: 所有的路径校验逻辑必须通过 `web_app.py` 的校验入口，严禁在业务接口内私自拼接路径。
*   **测试驱动**: 任何新参数的引入必须在 `test_web_api.py` 中增加相应的隔离与非法值测试。
*   **动态对齐**: 后端 API 的参数模型 (Pydantic Models) 应作为前端表单验证的唯一标准。
