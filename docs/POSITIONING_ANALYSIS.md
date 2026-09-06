# FileCortex 定位分析与竞品对照

> 目的：回答"这个项目是什么、和谁竞争、学什么、往哪走"
> 日期：2026-09-06 | 基线：v6.6.0

---

## 1. 产品定位（一句话）

**FileCortex 是一个本地优先（local-first）的"工作区上下文编译器 + 文件操作控制平面"**：帮用户在本地工作区中搜索、暂存、导出确定性的 AI 上下文，并执行经人工审视的文件操作，通过桌面/Web/CLI/MCP 四端暴露同一能力。

项目自述（CURRENT_ENGINEERING_PLAN）明确划定的边界：
- 原始文件是唯一事实源，应用只存配置与元数据；
- 不是云端 RAG/聊天产品，不强制账号/云模型；
- 不做自动化的破坏性 AI 操作。

这个定位是**清晰且差异化**的：它不做"又一个 AI 聊天"，而是做"AI 上下文的供给侧 + 文件治理的执行侧"。

## 2. 能力分解与竞品对照

FileCortex 的功能可拆成五个能力域，每个域都有成熟竞品，但**没有一个竞品同时覆盖五个域**：

| 能力域 | FileCortex 实现 | 直接竞品 | 竞品优势 | FileCortex 差异化 |
|--------|----------------|----------|----------|-------------------|
| A. 上下文打包（prompt 打包） | ContextFormatter: Markdown/XML、CDATA、蓝图、噪声消减、OOM/文件数上限 | **Repomix**、**code2prompt**、**gitingest**、files-to-prompt、Aider 的 /undo+repomap | Repomix：样式成熟、tree-sitter 符号压缩、安全扫描、token 统计；gitingest：URL→markdown 一键 | 四端统一（尤其 MCP 原生）；暂存区(staging)工作流——按需精选而非整仓倾倒；XML CDATA 工程化 |
| B. AI 原生接口（Agent 调用） | MCP Server：register/search/context/blueprint/stats | **@modelcontextprotocol/server-filesystem**、桌面搜索类 MCP | 官方 filesystem server 极简通用 | 带注册制沙盒+项目元数据（notes/tags/sessions）的 MCP，而非裸 FS 代理 |
| C. 文件搜索 | 4 模式（smart/exact/regex/content）+正负标签+gitignore | **Everything**(Windows 索引)、ripgrep/fzf、IDE 搜索 | Everything：NTFS USN 即时索引；rg：内容搜索黄金标准 | 与暂存/导出/标签联动的"面向 AI 工作流"的搜索，而非通用搜索替代品 |
| D. 文件治理（整理/查重/批量） | 批量重命名/删除/移动/归档/解压/查重/分类 | **Hazel**(macOS 规则自动化)、Dropover、各类 AI 文件整理器（如 QuiiBz/local-file-organizer） | Hazel：成熟规则引擎+监控；AI 整理器：LLM 自动分类 | 规则优先 + 失败可见 + 事务回滚 + 审计日志——"安全的半自动"而非"全自动黑盒" |
| E. 工作区编排 | 项目注册、置顶、暂存区、分组收藏、会话 | 无直接对标（最接近：IDE 的 workspace 概念 + Raycast/Alfred 的项目快速切换） | — | 把"AI 协作所需的文件集合"作为一等公民（staging+groups+sessions） |

**结论：FileCortex 的护城河不在任何单一能力，而在"五域贯通 + 安全边界 + 四端一致"。**

## 3. 值得学习的参考实现（按优先级）

| 参考 | 学什么 | 落到 FileCortex 的位置 |
|------|--------|----------------------|
| **Repomix** | 输出样式工程化：每文件头部带元数据、符号级压缩、secret 扫描报告、token 精确计数 | Phase 3 Context Compiler 的直接蓝本；其 "select files via glob" 与 staging 互补 |
| **Aider repomap** | tree-sitter 抽符号图 + PageRank 排序，用极少 token 表达仓库结构 | Phase 3 的 repository map；蓝图(blueprint)的进化方向 |
| **gitingest / files-to-prompt** | 极简 UX：一条命令/一个 URL 得到可粘贴上下文 | fctx.py 的 `export` 可加 `--stdin/--clip` 直达剪贴板 |
| **@modelcontextprotocol/server-filesystem** | MCP 工具的极简语义与错误约定（isError 标记） | mcp_server.py 的错误应从字符串改为协议级 isError；补 categorize/copy 等工具 |
| **Everything / rg** | 索引与内容搜索的极致性能 | Phase 4 SQLite/FTS5 增量索引；短中期先把 content 搜索换 rg 后端（可选） |
| **Hazel** | 规则引擎 + dry-run 预览 + 审计 + undo | Phase 4 "规则优先分类计划"的安全范式（项目已明确 model 建议永不直接动文件） |
| **uv / ruff 的发布工程** | 单二进制分发、跨平台 CI、clean-install 冒烟 | Phase 2 发布工程：Windows/macOS CI、wheel 安装冒烟、Playwright E2E |

## 4. SWOT

| | 有利 | 不利 |
|---|------|------|
| **内部** | 四端一核；安全/事务纪律强；测试文化罕见地好；文档-守卫联动 | 三个 God Object；四入口行为碎片化；GUI/前端零执行级测试；Tk 桌面版维护成本高 |
| **外部** | MCP 生态爆发期，"带沙盒的工作区 MCP" 生态位空着；本地优先/隐私优先思潮；LLM 上下文工程成为显学 | Repomix/gitingest 在打包域迭代极快；IDE/编辑器原生集成 AI 上下文（Cursor 等）挤压独立工具空间；Everything/rg 在各自域几乎不可超越 |

**战略含义**：不要在 A 域与 Repomix 拼打包样式、不在 C 域与 rg 拼搜索速度——把 B（MCP）与 E（编排/暂存）做深，A 域做到"够用且确定性强"，D 域保持"安全的半自动"。

## 5. 路线图建议（对既有 ROADMAP 的细化）

### Phase 1（进行中）：可用性 — *让安全的功能好用*
1. 最近目标/目标预设（copy/move/extract）
2. 上下文右键动作 + 每项结果明细（已完成一半：本轮 execute 跳过项已可见）
3. 键盘导航 + ARIA（前端事件委托已有基础）
4. 首次运行引导 + 操作历史
- **验收**：无模糊目标的破坏性操作；每个批量结果有 completed/skipped/failed+原因。

### Phase 2：可维护性与发布工程 — *降低后续一切成本*
1. 统一授权依赖 `verify_registered_path()`（本轮 A1 结构性结论）
2. DataManager 拆 ConfigStore/ProjectService；main.js/file_search.py 按 feature 拆分
3. WS 工具流超时 + stream_tool 孙进程治理（Job Object/killpg）
4. Windows/macOS CI + wheel clean-install 冒烟 + Playwright E2E（open→search→stage→generate 一条链）
5. 四入口策略对象统一（excludes 组合/上限/错误处置）
- **验收**：clean env 安装即冒烟通过；平台敏感行为在 Windows CI 上被真实执行。

### Phase 3：上下文编译器质量 — *在加聊天产品之前先把供给侧做好*
1. JSON manifest（path/hash/size/token/truncation/reason）+ 确定性 recipe
2. 精确 tokenizer + 硬 token 预算
3. tree-sitter 符号图 + `full/symbols/tree-only/exclude` 详情级别（学 Repomix/Aider）
4. git diff 感知排序；secret 扫描报告
- **验收**：相同输入+配置 → 逐字节确定的 manifest。

### Phase 4（可选）：本地索引与受审视的整理
1. SQLite/FTS5 增量索引（文件名/内容/符号）
2. 可选本地嵌入/重排（永不强制云）
3. PDF/DOCX/HTML/OCR 可选解析
4. 规则优先 + dry-run + 冲突预览 + 审计 + undo 的分类计划（学 Hazel）
- **验收**：模型建议永远不直接动文件，必须人工批准具体计划。

### 明确的非目标（维持既有立场）
- 不做云模型/向量库/账号；不做自动破坏性 AI；不替代文件管理器/IDE/RAG 平台；JSON 配置未证实时不引入数据库迁移。

## 6. 定位一句话（面向用户）

> "给 AI 喂对上下文、替你安全地动文件——一个本地跑、四端通、每一步可审视的工作区编排助手。"
