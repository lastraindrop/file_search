# FileCortex 全面评审与落地方案报告

> 基线：v6.6.1（2026-09-09）| 评审日期：2026-09-17
> 评审方法：全部后端源码逐文件人工审读（core 10 模块 + routers 8 模块 + 4 入口）+ 前端 7 模块与桌面版子代理深审 + 实测验证（pytest / ruff）
> 实测基线：**864 passed, 0 failed（303s）；Ruff 0 errors**
> 性质：独立复核报告。对既有 `docs/ARCHITECTURE_REVIEW.md`、`docs/POSITIONING_ANALYSIS.md` 的结论做验证与补充，**不重复**已归档问题；新发现以台账形式给出（§4）。

---

## 实施交付记录（2026-09-17，v7.0.0 已完成）

> 本报告的 §4 台账与 §5 落地方案已按计划实施完毕，最终验证：**882 passed / Ruff 0 errors / clean-install 冒烟 SMOKE-OK / wheel 7.0.0 构建通过**。

### 修复交付（§4 台账）

| 类别 | 已修复 | 保留/延后（原因） |
|---|---|---|
| 后端 | BE-1 嵌套 gitignore、BE-2 `%%` 引号、BE-3 CLI 导出沙盒、BE-4 空查询短路、BE-5 哨兵对齐、BE-6 progress schema、BE-7 atexit 累积、BE-8 写回守卫 | — |
| Web | WEB-2 导出/统计异步化 | WEB-1（任意回环端口为测试锚定的设计决策）、WEB-3（双行为被现有测试锁定）、WEB-4（IO 放大降级为后续优化） |
| 前端 | FE-1/2（openProject 取消搜索 + flush 暂存）、FE-3 全选可见性、FE-4 同文件确认、FE-5 notes 守卫、FE-6 剪贴板真值、FE-7 Modal 去重、FE-8 静默去抖、FE-9 stats 序号、FE-10 fav 恢复守卫、FE-11 ResizeObserver、FE-13 菜单实测、FE-14 fetch 超时、FE-15 预览清空 | FE-12（追加渲染性能，降级为后续优化） |
| 桌面 | DT-1 预览后台读、DT-2 导出/全选后台化、DT-3 防御守卫、DT-4 状态覆盖、DT-5 守护、DT-6 finally 恢复、DT-8 过滤去抖、DT-9 全量复制、DT-10 删后模型同步+索引、DT-11 有界排空、DT-12 重命名去抖、DT-13 重入守卫、DT-14 死样式 | DT-7（跨线程 after 保持既有 try 包裹模式）、DT-2 的 `copy_project_tree` 分支 |
| 契约 | CN-1（=BE-5）哨兵对齐 | CN-2（CLI excludes 行为变更）、CN-3（MCP isError 需 SDK 环境）、CN-4（私有导出兼容层） |

### 发行工程交付（§5 方案）

- [x] `FCTX_CONFIG_DIR` 配置/日志目录重定位 + `GET /healthz` 免鉴权探活（web_app.py:245）
- [x] `docker/Dockerfile`（非 root + HEALTHCHECK + 单 worker）、`docker/docker-compose.yml`
- [x] `scripts/filecortex.service`（systemd）、`scripts/install_service_windows.bat`（NSSM）
- [x] `scripts/smoke_install.sh` / `smoke_install.ps1`（clean-venv → CLI → Web，实测 SMOKE-OK）
- [x] `.github/workflows/build.yml`（wheel 内容断言 + 冒烟）、`docker.yml`（镜像构建 + 鉴权验证）
- [x] README 部署拓扑化 + `DEVELOPER_GUIDE` 反模式 #19–23 + ROADMAP/工程计划同步
- [x] 版本 7.0.0（`__init__.py` / `pyproject.toml` / 文档守卫联动）
- [x] 回归测试 `tests/test_v7_release_engineering.py`（18 项）+ 全量 882 passed

### 与 §5.7 六周计划的对照

R1/R2/R3 修复批与 L1/L2 落地批已在单轮内完成（含验证与文档同步）；剩余 Low 级优化项（FE-12、WEB-4、DT-7、CN-2/3/4）按原计划保留为后续批次。

---

## 0. 执行摘要（TL;DR）

1. **健康度：优秀。** 架构分层清晰（入口层 → 适配层 → 领域层 → 资源层）、依赖单向无环、安全原语（PathValidator）与配置持久化协议（跨进程锁 + 三方合并 + 原子替换）质量高于绝大多数同规模开源项目；864 项测试 + Ruff 全绿，且测试与历史修复注释一一对应，可追溯性极好。
2. **主要债务仍然是结构性的**：安全检查"分布式"（每条路由手工重复授权组合）、三个 God Object（`DataManager`/`FileCortexApp`/`main.js`）、四入口行为碎片化。这三条与既有架构审查结论一致，本次复核予以确认，且新增若干佐证。
3. **本轮新发现 41 项问题**（后端/内核 8、Web 层 4、前端 15、桌面 14），**无高危安全漏洞**；最高严重度为 4 项 Medium（均为状态一致性竞态或主线程 IO 冻结），其余为 Low。XSS/CSRF/路径穿越/Zip 炸弹/UNC 泄漏等历史攻击面经本轮独立复核均未见回归。
4. **定位清晰且差异化成立**："本地优先的工作区上下文编译器 + 文件操作控制平面"，护城河在"五域贯通 + 安全边界 + 四端一致"，而非任何单一功能。2026 年竞品格局下（Repomix/gitingest 打包域、官方 filesystem MCP、IDE 原生 AI），建议继续做深 MCP + 编排/暂存域。
5. **落地方案（§5）**：项目本体已是完整系统，"轻量完整可落地"的正确形态是**发行工程**而非重写——定义 Lite（core+web+CLI+MCP）/ Full（+桌面）两级发行，补齐 Docker/systemd/NSSM 部署工件、配置目录环境变量化（`FCTX_CONFIG_DIR`）、clean-install 冒烟门禁，六周内可交付可安装、可部署、可验收的 v7.0。

---

## 1. 验证基线（本次实测）

| 项 | 命令 | 结果 |
|---|---|---|
| 单元/回归测试 | `python -m pytest` | **864 passed, 0 failed**（303.41s） |
| Lint | `python -m ruff check .` | **All checks passed** |
| 打包元数据 | pyproject.toml | wheel 含 templates/static/gui；`fctx`/`fctx-web`/`fctx-mcp` 三个 script 入口 |
| CI | .github/workflows/{test,lint}.yml | 存在且与本地基线一致 |

结论：仓库声明的质量指标与实测一致，无"文档虚报"。

---

## 2. 架构与工程评审

### 2.1 分层与依赖（复核确认）

```
入口层   file_search.py(Tk)  web_app.py(FastAPI)  fctx.py(CLI)  mcp_server.py(MCP)
适配层   routers/{project,fs,action,ws}_routes + services + schemas + common
领域层   file_cortex_core/{security,config,file_io,format_utils,search,context,actions,duplicate,process_utils,gui}
资源层   本地文件系统 + ~/.filecortex/config.json（唯一持久化）
```

复核结论：
- **依赖方向验证无环**：`security` 为零依赖根；core 不 import 任何入口/框架（FastAPI 仅出现在 routers，Tk 仅在 gui/）；四入口全部复用同一内核——微内核承诺属实。
- **唯一持久化是 JSON 配置**：原始文件是唯一事实源的产品不变量（CURRENT_ENGINEERING_PLAN）在代码中得到忠实执行（notes/tags/sessions/staging 均为元数据）。
- **WS 适配层的线程桥接**（`_make_enqueue` 背压 + `stop_event` 分片等待）是同类项目里少见的正确实现，且处理了 Python 3.10/3.11 的 `TimeoutError` 语义分裂。

### 2.2 工程优点（保持项，含新佐证）

| # | 优点 | 本轮新佐证 |
|---|------|-----------|
| 1 | 安全原语单点收口：`PathValidator.is_safe` 双平台语义、长前缀剥离、`\\?\UNC` 变体拦截、symlink resolve | 复核 `extract_archive` 的 UNC 前置拦截（在任何 `resolve()` 触发 SMB 之前）与 `validate_project` 的 SUBST/符号链解析后二次校验，防御纵深成立 |
| 2 | 配置持久化协议完整（RLock + 跨进程 owner 锁 + TOCTOU 重读 + 三方合并 + `os.replace` + PermissionError 重试） | `save()` 对损坏盘上配置的"先备份 `.corrupt-<ts>` 再重写"路径复核无误 |
| 3 | 事务性文件操作：extract 三阶段 + 四重 Zip 资源限制；批量 copy/rename 回滚 | `batch_rename` 对"大小写不敏感文件系统上的纯大小写重命名"判定为同源不冲突——这是多数项目会踩的坑 |
| 4 | 并发纪律：共享搜索池的 `RuntimeError` 重建路径、`CancelledError`（BaseException）显式捕获、CANCELLED 态 future 的显式收割 | `search_generator` 最终 drain 的 `f.done()` 显式收割避免了 `wait()` 永不报告 CANCELLED 的坑，注释解释充分 |
| 5 | 测试文化与文档-代码联动：BUG-W*/B*/C* 系列注释与回归测试一一对应 | 864 项测试按修复批次归档，`test_frontend_contract.py` 对 JS 源码做契约静态断言（无头验证前端结构） |
| 6 | 前端竞态防护：`previewRequestId`/`searchGeneration`/`flushNow`/socket 身份校验 | 独立复核 XSS 面全干净：innerHTML 一律 `escapeHtml`（含引号防属性注入）、markdown 走 marked+DOMPurify、CSP 与实际 CDN 精确对齐 |

### 2.3 结构性债务（对既有 A1–A7 的复核 + 新增）

**确认既有结论**（详见 `docs/ARCHITECTURE_REVIEW.md` §3，此处仅列状态）：

| 编号 | 问题 | 本次复核状态 |
|---|---|---|
| A1-高 | 安全检查分布式，缺统一授权依赖 | 确认：`get_valid_project_root + is_path_safe` 组合仍手工出现在 ≥12 端点；v6.6.0 后未再发现旁路，但模式性风险仍在（新增端点忘写即漏） |
| A2-中 | 三个 God Object（DataManager ~20 方法 / FileCortexApp ~2000 行 / main.js App ~1600 行） | 确认，且是新 BUG 的温床：本轮前端 Medium 竞态 2 项、桌面 Medium 冻结 2 项全部落在这两个 God Object 里 |
| A3-中 | import 副作用（logger 建目录、模块级线程池） | 确认，无恶化 |
| A4-中 | 四入口行为碎片化 | 确认并新增佐证：CLI `search` 不使用项目配置的 excludes（`fctx.py:153` 传 `args.excludes or ""`，而 WS 用 `proj_config["excludes"]`）；MCP 搜索硬截 50 条 |
| A5-低 | 队列哨兵元组未类型化、response_model 缺失 | 确认，并新发现哨兵契约不一致一处（见 CN-1） |
| A6-低 | 名义 DI 事实全局 | 确认：`ACTIVE_PROCESSES = process_manager._processes` 仍导出私有 dict 本体 |
| A7-低 | IO 放大（get_metadata 先于命中判断；同文件三次打开；小改动全量保存协议） | 确认，无恶化 |

**新增结构性观察**：

| 编号 | 观察 | 说明 |
|---|---|---|
| S-1 | **嵌套 .gitignore 不生效** | `FileUtils.get_gitignore_spec` 只读取项目根的 `.gitignore`（file_io.py:164），`walk_filtered` 全程只用这一份 spec 匹配。子目录内的 `.gitignore`（monorepo 常见）完全被忽略——与 git 语义不一致，用户会误以为已被排除的文件仍进入搜索/导出。属功能正确性缺口（见 BE-1） |
| S-2 | **单文件配置是容器化/多实例的硬约束** | `get_app_dir()` 硬编码 `~/.filecortex`，容器多实例/多用户共享一份 config.json；§5 落地方案给出 `FCTX_CONFIG_DIR` 环境变量化改造 |
| S-3 | **进度追踪为进程内存态** | `ProgressTracker` 类级 dict，README 已注明"必须单进程部署"——这是发布工程约束，需在部署工件中固化（单 worker） |
| S-4 | **Web 层同步阻塞端点** | `generate_context`/`api_stage_all`/`stats` 等 `def` 端点在 Starlette 线程池中同步做长 IO（最多 500 文件/50MB），高并发下线程池占满会拖慢全站——单人使用无碍，LAN 多用户需注意（见 WEB-4） |
| S-5 | **`_detect_encoding` 的 lru_cache 键含绝对路径字符串** | 大仓库长会话下 cache（maxsize=128）抖动，且不同大小写拼法的同一路径在 Windows 上重复缓存；影响极小 |

---

## 3. 定向与定位分析（对既有定位报告的独立复核与 2026 视角更新）

### 3.1 定位复核

既有定位（`docs/POSITIONING_ANALYSIS.md`）：**"本地优先的工作区上下文编译器 + 文件操作控制平面"**，五能力域（A 上下文打包 / B AI 原生接口 / C 文件搜索 / D 文件治理 / E 工作区编排）。

本次复核**同意该定位且认为代码实现与定位自洽**：
- "上下文供给侧而非聊天产品"：仓库里没有任何 LLM 客户端调用，导出确定性（同输入同配置 → 同字节输出）作为不变量被测试锁定；
- "安全边界"：注册制沙盒 + 每路径校验 + UNC 拦截，是把"给 AI 喂文件"这件事当安全工程做的稀有样本；
- "文件治理的安全半自动"：所有批量操作 dry-run/回滚/逐项失败报告，与"全自动 AI 整理器"划清界限。

### 3.2 竞品矩阵（2026-09 视角，扩展现有表格）

| 能力域 | FileCortex v6.6.1 | 主要竞品（2026 格局） | 差距/优势判读 |
|---|---|---|---|
| A 上下文打包 | MD/XML+CDATA、蓝图、噪声消减、OOM 上限；**token 仅为 4:1/1.5:1 启发式估算** | **Repomix**（符号压缩、secret 扫描、精确 token）、**gitingest**（URL 一键）、files-to-prompt | 打包样式工程化差距仍大；但 staging 精选工作流 + XML CDATA 是差异化 |
| B AI 原生接口 | MCP：register/search/context/blueprint/stats，带注册制沙盒 | **@modelcontextprotocol/server-filesystem**（裸 FS 代理，无沙盒）；各 IDE 内建 MCP 宿主 | **生态位仍然空着**："带安全边界的 workspace MCP"；MCP 采用率 2025-2026 持续走高，窗口仍在但收窄 |
| C 文件搜索 | 4 模式 + 正负标签 + gitignore（仅根级） | **Everything**（USN 索引）、**ripgrep**、IDE 索引 | 不应追赶；content 模式可考虑可选 rg 后端 |
| D 文件治理 | 批量重命名/删除/移动/归档/解压/查重/分类，全带回滚与审计 | **Hazel**（macOS）、AI 整理器（LLM 自动分类） | "规则优先 + 失败可见 + 事务回滚"定位正确 |
| E 工作区编排 | 注册、置顶、staging、分组、会话 | 无直接对标（IDE workspace + Raycast 项目切换最接近） | 独有域，建议做深（操作历史、staging 快照/恢复） |

### 3.3 值得学习的参考点（按投入产出排序）

1. **Repomix 的输出工程**：每文件头部元数据、tree-sitter 符号级压缩、secret 扫描报告、精确 tokenizer——Phase 3 的直接蓝本（与既有结论一致，维持）。
2. **Aider repomap**：PageRank 排序的符号图，用极少 token 表达仓库结构——blueprint 的进化方向。
3. **官方 filesystem MCP 的错误约定**：`isError` 协议级标记（本项目 MCP 工具目前返回 `"Error: ..."` 字符串）——小改动大收益。
4. **uv/ruff 式发布工程**：单命令安装、跨平台 CI、clean-install 冒烟——正是 §5 落地方案的核心内容。
5. **Hazel 的规则引擎范式**：dry-run 预览 + 审计 + undo——Phase 4 分类计划的安全范式。

### 3.4 战略建议（一句话版）

不在 A 域与 Repomix 拼样式、不在 C 域与 rg 拼速度；**把 B（带沙盒的 workspace MCP）与 E（staging/编排）做深，A 域做到"确定性 + 可预算"，D 域维持"安全半自动"**；短期最高杠杆是 §5 的发行落地——项目工程素质已经配得上被真实部署，缺的只是最后一公里。

---

## 4. 完整 Code Review —— 新发现 BUG 台账

> 范围：v6.6.1 全源码。**已收录于既有 docs/ 并标注"已修复/已知"的问题不再列出**（如 A4 入口碎片化矩阵、A7 IO 放大等结构性项以 §2.3 呈现）。
> 严重度定义：High=数据丢失/安全漏洞/崩溃；Medium=可复现的功能错误或明显体验劣化；Low=边角缺陷/一致性瑕疵/潜在隐患。
> 每项均经源码定位复核；前端/桌面项由专项深审给出行号，修复前建议按行号二次确认上下文未变。

### 4.1 后端 / 内核（BE）

| # | 位置 | 严重度 | 问题 | 建议 |
|---|---|---|---|---|
| BE-1 | `file_io.py:164`（`get_gitignore_spec`） | **Medium** | 只编译项目根 `.gitignore`，子目录 `.gitignore` 全部不生效，与 git 语义不一致；monorepo 下排除规则失真，搜索/导出/stage_all 均受影响 | walk 时逐目录合并 gitignore spec（pathspec 支持叠加）；或文档明示限制 |
| BE-2 | `actions.py:1027`（`win_quote`） | Low | Windows shell 模式下把路径中 `%` 替换为 `%%`——`%%` 折叠仅在**批处理文件**中生效，`cmd /c` 命令行上下文会保留双 `%`，含 `%` 的路径被改写 | 命令行上下文用 `"%VAR%">nul"` 类转义或 `^%`；至少加注释与测试 |
| BE-3 | `fctx.py:213-218`（`cmd_export`） | Low | `--output` 相对路径锚定项目根但**未做 is_safe 校验**，`-o ../x.md` 可写出项目外，违反工程不变量 #2（写路径须过沙盒） | 写入前 `PathValidator.is_safe(out_path, proj_root)`，越界报错 |
| BE-4 | `search.py:335` | Low | content 模式空 query 时仍全树扫描（walk 完整执行、零产出），CLI 不拦空 query 时浪费明显 | 入口处对 `mode=="content" and not query.strip()` 提前返回 |
| BE-5 | `duplicate.py:137-139` | Low | 异常路径只发 `("ERROR", e)` 不发 DONE 哨兵；`SearchWorker` 是 ERROR+DONE 双发（search.py:505-508）——队列哨兵契约不一致，未来新消费者按"必等 DONE"实现会挂死 | 对齐 SearchWorker：ERROR 后补发 DONE；长期看 A5 的类型化哨兵 |
| BE-6 | `fs_routes.py:448/464` | Low | `/api/fs/progress`、`/api/fs/progress/new` 入参为裸 `dict[str, Any]`，绕过 schemas.py 的校验纪律（项目其余端点全部 Pydantic 化） | 补 `ProgressPollRequest`/`ProgressNewRequest` 模型 |
| BE-7 | `search.py:38` | Low | 模块级 `SHARED_SEARCH_POOL` 构造是 import 副作用（A3 已记）；新增：`_reinit_shared_pool` 每次重建都会 `atexit.register` 累积回调（无界但实际触发次数少） | reinit 时先尝试移除旧回调，或改 lazy init |
| BE-8 | `config.py:761` | Low | `update_project_settings` 末尾用 `PathValidator.norm_path(project_path)` 直接入 map，未经 `get_project_data_obj` 的空值防御；当前调用链前置了注册校验，属纵深缺失 | 复用 `get_project_data_obj` 或加空值断言 |

### 4.2 Web 层（WEB）

| # | 位置 | 严重度 | 问题 | 建议 |
|---|---|---|---|---|
| WEB-1 | `web_app.py:82-85`（`_origin_allowed`） | Low | Origin 门禁放行**任意回环端口**，而 `CORSMiddleware` 白名单只有 8000 端口——两层策略不对齐。实际风险被 CORS 预检（JSON POST 必预检）+ FastAPI content-type 校验缓解，但本地恶意页面理论上可让简单请求服务端执行 | 收紧为"回环 + 显式端口集"，或文档明示这是 dev 工作流取舍 |
| WEB-2 | `action_routes.py:42-82`（`generate_context`） | Medium（体验/资源） | 同步端点内联最多 500 文件/50MB 的读取与格式化；默认 Starlette 线程池 40 线程，LAN 多用户并发 2-3 个大导出即可占满线程池，拖慢全站所有端点（含搜索 WS 的 to_thread） | 改 `async def` + `asyncio.to_thread`（与 MCP 对齐）或引入导出任务队列 + ProgressTracker |
| WEB-3 | `ws_routes.py:36-47` | Low | `verify_ws_token` 每次握手重新 `os.getenv`，与 `web_app.API_TOKEN` 模块级快照不同步：运行中改环境变量（或测试里 patch `web_app.API_TOKEN`）会出现 HTTP/WS 鉴权不一致 | 读取同一模块级常量 |
| WEB-4 | `services.py:69-116`（`get_children`） | Low | 每个条目 `ep.resolve()` + `get_node_info`（内含二次 resolve+stat）；大目录（数千条目）单次展开数秒且重复 IO（A7 模式在树端的具体化） | 复用一次 stat 结果；跳过 resolve（scandir 条目已在目标目录内） |

### 4.3 前端（FE）—— vanilla JS/ES6 模块

| # | 位置 | 严重度 | 问题 |
|---|---|---|---|
| FE-1 | `main.js:284-288` | **Medium** | `refreshProject()` 未 flush 暂存区 500ms 去抖（`syncStagingToBackend`）即调 `openProject()` 从服务端重建 staging——Copy/Extract/Stage-All/刷新前 500ms 内的暂存增删被静默回滚。同类竞态在 `categorizeStaged` 已用 `flushNow()` 修过（main.js:945），此路径漏用 |
| FE-2 | `main.js:223-282` | **Medium** | `openProject` 不取消在途搜索：切换项目后旧 `/ws/search` socket 仍在流式返回，旧项目结果持续灌入新项目的搜索态与覆盖层（应像 `stopSearch` 一样 bump `searchGeneration`/关 socket） |
| FE-3 | `main.js:1328,1353` | Low | 全选可见性检查读 `#searchResultsList.style.display`，但实际切换的是父级 `#section-searchResults`（main.js:1801-1807）——隐藏的搜索结果仍被计入全选/批量按钮态，"全选"会选中不可见项 |
| FE-4 | `main.js:439-452` | Low | 未保存编辑守卫只覆盖"切换到不同文件"；重新点击**同一文件**会直接重拉内容丢弃编辑且无确认 |
| FE-5 | `main.js:545` | Low | `projConfig.notes` 写路径无 `|| {}` 防护（读路径 :534 有）；配置载荷缺 notes 键时抛异常 → 用户看到"保存失败"但服务端实际已保存，本地态未更新（当前后端模型默认有 notes，属潜伏） |
| FE-6 | `state.js:147-149` + `main.js:511-529,1668-1674` | Low | `copyToClipboard` 失败返回 false，但 `copyPath`/`collectPaths` 无条件 toast "已复制"——纯 HTTP LAN 部署（无 clipboard API）下是假成功 |
| FE-7 | `ui.js:337`、`main.js:90,321,372,964,1647` | Low | 反复 `new bootstrap.Modal(el)` 而非 `getOrCreateInstance`：长会话累积实例，存在重复 transition/backdrop 回调风险 |
| FE-8 | `main.js:804-811`（经 :29-35 去抖） | Low | 清空搜索框触发去抖 `startSearch` → `!query.trim()` 分支弹"请输入搜索关键词"警告——被动清空 400ms 后弹出无端提示 |
| FE-9 | `main.js:1221-1254` | Low | `_updateStatsImpl` 无请求序号守卫（previewFile/openProject 都有），慢的旧 stats 响应可覆盖新暂存态的 token 徽章 |
| FE-10 | `main.js:1724-1732` | Low | `ctxAction('fav')` 临时换 `state.currentFile`，POST 在途期间用户预览别的文件后 finally 恢复旧值 → currentFile 与预览 pane 失同步 |
| FE-11 | `virtual-list.js:1-4` | Low | 固定 `rowHeight=76` 无 ResizeObserver：snippet 换行/缩放/主题变化时行高漂移；面板拖拽后可视切片过期 |
| FE-12 | `main.js:1001,1022,1044` | Low（性能） | 工具输出循环 `modalBody.innerHTML +=`（整段重解析）与 `outputDiv.innerText +=`（O(n) 重排）——长输出时前端卡顿 |
| FE-13 | `main.js:1697-1700` | Low | 右键菜单尺寸硬编码 180×200，条目增多/高主题时会裁切出屏 |
| FE-14 | `api.js:8-35` | Low | `_fetch` 无超时/AbortController：请求悬挂时按钮永久停留在"Generating…/Archiving…"禁用态 |
| FE-15 | `main.js:649-651,669-673` | Low | 重命名/删除后预览 pane 仍显示旧文件内容（currentFile 已清但 `#codePreview` 未清） |

**前端安全复核（通过项）**：XSS 面全干净（innerHTML 一律 escapeHtml 且含引号、marked+DOMPurify、mermaid 输入转义）；CSP 与 CDN 白名单精确对齐；WS 生命周期的 generation/socket 身份守卫正确。

### 4.4 桌面 Tkinter（DT）

| # | 位置 | 严重度 | 问题 |
|---|---|---|---|
| DT-1 | `file_search.py:1363-1374` | **Medium** | 每次树选择在 **Tk 主线程**同步读最多 `preview_limit_mb`（可配 100MB）——方向键浏览结果时逐条读文件，UI 冻结 |
| DT-2 | `file_search.py:1630-1659`（另 :810-819、:1463） | **Medium** | `copy_all_staging_content`/`on_stage_all`/`copy_project_tree` 同步执行 500 文件/50MB 级导出或全项目扫描——主循环阻塞数秒 |
| DT-3 | `file_search.py:1338` | Low | `on_tree_select_preview` 的 `elif tree == self.tree_staging or tree == self.tree_fav` 分支不可达（两树未绑定 `<<TreeviewSelect>>`）——暂存/收藏页签选择无预览（死代码 + 功能缺失并存） |
| DT-4 | `file_search.py:791-793` | Low | 载入触发的搜索：`trigger_search()` 置"扫描中..."后立即被 793 行"已就绪"覆盖，扫描期间状态栏显示错误 |
| DT-5 | `file_search.py:1978` | Low | `ctx_add_to_favorites` 缺 `if self.current_proj_config` 守护（所有兄弟方法都有），无项目时可 AttributeError 逃入 Tk 回调 |
| DT-6 | `file_search.py:949-978` | Low | `_render_tool_results` 异常路径未恢复 `tools_scroll` 为 DISABLED——渲染失败后日志区可被用户编辑 |
| DT-7 | `file_search.py:943,1056` | Low | worker 线程直接 `root.after()`（Tkinter 官方不支持跨线程）；已有 try/except 包裹，关停期偶发 TclError——应统一走队列+主线程泵 |
| DT-8 | `file_search.py:1471-1515` | Low | 暂存过滤输入 trace（:472-474）每击键全量重建树 + 逐项 stat；暂存文件消失时同步写盘配置——输入卡顿 + IO 放大 |
| DT-9 | `file_search.py:1843-1845` | Low | "复制路径"遍历树子项：过滤视图激活时只收集**可见项**，静默漏掉被过滤的暂存文件 |
| DT-10 | `gui/duplicate_finder.py:157,231-278` | Low | `delete_selected` 不更新 `self.duplicate_groups` 内存模型（只删树节点），且逐文件 O(n²) 重扫所有组——删除后组数统计可错 |
| DT-11 | `gui/duplicate_finder.py:129-178` | Low | 轮询单 tick 无界排空队列（搜索轮询是 100/tick 上限）——数千查重组时单帧插入全部 |
| DT-12 | `gui/batch_rename.py:100,105` | Low | dry-run 预览每击键同步执行（正则编译 + N×is_safe + exists）——大选择集输入滞后（应去抖） |
| DT-13 | `gui/path_collection.py:182` | Low | 回调内 `self.update()` 处理全部挂起事件——双击可重入处理器造成双复制/二次 destroy(TclError)；应 `update_idletasks()` |
| DT-14 | `gui/duplicate_finder.py:106` | Low | 引用未定义的 ttk 样式 `Danger.TButton`（仅存在 `Accent.TButton`）——静默回退默认样式（死引用） |

**桌面复核（通过项）**：搜索轮询单 after 链 + DONE 哨兵 TOCTOU 防护（:1217-1276）验证无误；线程快照纪律（Tk 变量主线程快照、worker 走队列）整体好于典型 Tk 应用。

### 4.5 一致性 / 契约（CN）

| # | 位置 | 严重度 | 问题 |
|---|---|---|---|
| CN-1 | `search.py:505-508` vs `duplicate.py:137-139` | Low | 队列哨兵契约不一致（=BE-5，跨入口归档）：SearchWorker ERROR 后补 DONE，DuplicateWorker 只发 ERROR |
| CN-2 | `fctx.py:153` vs `ws_routes.py:127` | Low | CLI 搜索不读项目配置 excludes（Web 读）——A4 矩阵的又一实例，用户同一项目两端搜索结果不同 |
| CN-3 | `mcp_server.py` 全部工具 | Low | MCP 错误以 `"Error: ..."` 字符串返回而非协议级 `isError` 标记（官方 filesystem server 约定）——Agent 侧无法机判成败 |
| CN-4 | `common.py:97-98` | Low | `ACTIVE_PROCESSES`/`PROCESS_LOCK` 导出 ProcessManager 私有内部（A6 的具体化）：任何旧代码绕过容量/锁语义直接改 dict |

### 4.6 健康性总评

- **无 High 级发现**。四轮历史加固（6.5.2→6.6.1）已清掉全部已知高危；本轮独立攻击面复核（XSS/CSRF/CSWSH/路径穿越/Zip 炸弹/UNC/PID 复用/配置竞态）未见回归。
- 4 项 Medium 集中于两类：**前端状态一致性竞态**（FE-1/2）与**桌面主线程 IO**（DT-1/2）+ **BE-1 嵌套 gitignore**——全部落在既有结构性债务（God Object、A7 IO 模式）的预测范围内，佐证 A2/A7 应优先偿还。
- 测试盲区与既有结论一致：GUI/前端无执行级测试（本轮 29 项 FE/DT 发现中 0 项可被现有 864 测试捕获）。

---

## 5. 轻量完整系统落地方案（v7.0 "可部署发行"）

> 判断依据：项目本体已是功能完整的系统（四端 + 864 测试）。"轻量但完整、实际可落地"的正确实现**不是重写，而是发行工程（release engineering）**：定义最小可信发行集、补齐部署工件与门禁、消除部署硬约束。以下方案全部基于现有代码结构，改动量可控（预估核心代码改动 < 300 行，其余为新增工件与 CI）。

### 5.1 目标与非目标

**目标**
1. 一条命令安装（`pipx install file-cortex`）、一条命令起服务（`fctx-web`）、一条命令进 AI（MCP 注册）。
2. 三种部署拓扑开箱即用：单用户桌面/本机、LAN 团队服务器、CI/headless。
3. 干净环境安装即冒烟（clean-install smoke）成为发布门禁。
4. 保持既有非目标：不做云模型/账号/自动破坏性 AI。

**非目标**：不重写内核；不引入数据库；不砍功能域——"轻量"通过**发行分级 + 部署简化**实现，而非裁剪能力。

### 5.2 发行分级

| 发行 | 内容 | 安装 | 适用 |
|---|---|---|---|
| **Lite（默认）** | core + Web + CLI + MCP（`file-cortex` wheel，现有默认依赖即 Lite——FastAPI 栈无 GUI 依赖） | `pipx install file-cortex` | 服务器/CI/大多数用户；无头环境自动降级（`__init__.py` 的 tkinter ImportError 守护已存在） |
| **Full** | Lite + Tk 桌面 | `pipx install "file-cortex[gui]"` + `python file_search.py`（或 PyInstaller exe：`build_exe.py` 已就绪） | 需要原生桌面的用户 |
| **MCP-only** | stdio 传输 | `pip install mcp` + Claude Desktop/Cline 注册（README 已有配置样例） | AI Agent 宿主 |

配套调整（小改动）：
- `pyproject.toml` 增加环境标记分类（`Desktop :: Tkinter` 可选）；
- 桌面相关 `file_search.py` 与 `gui/` 保留在仓库与 wheel 中（不裁剪），仅文档层面标注 Full 发行支持等级（桌面 bug 台账 DT-* 修复排入 Phase 2，见 §5.7）。

### 5.3 部署硬约束的消除（唯一必需的内核改动）

| 约束 | 现状 | 改造 |
|---|---|---|
| 配置目录固定 `~/.filecortex` | 容器/多实例共享一份 config | `get_app_dir()` 优先读 `FCTX_CONFIG_DIR` 环境变量（config.py 单点改动 + 测试） |
| 进度追踪进程内存态 | 必须单 worker（README 已注明） | **维持现状**，在部署工件中固化 `--workers 1`；中长期若需多进程再评估（违反"JSON 未证实时不迁移"原则） |
| 鉴权默认仅 localhost | LAN 部署需 token | 已支持（`FCTX_API_TOKEN` 强制非 loopback 绑定），部署模板中示例化 |

### 5.4 部署拓扑与工件（附录 A 给出全文）

**拓扑 1：单用户本机**（默认，零配置）
```
pipx install file-cortex && fctx-web          # http://127.0.0.1:8000
```

**拓扑 2：LAN 团队服务器（Docker，单容器单 worker）**
- 附录 A.1 `docker/Dockerfile`：`python:3.12-slim` + wheel 安装 + 非 root 用户 + `HEALTHCHECK /api/whoami` + `ENV FCTX_CONFIG_DIR=/data`；
- 附录 A.2 `docker-compose.yml`：卷挂载 `/data`（配置）与工作区目录、`FCTX_API_TOKEN` 必填、`FCTX_ALLOWED_ORIGINS` 示例；
- 镜像体积预估 < 200MB（slim + FastAPI 栈）。

**拓扑 3：Windows 常驻服务**
- 附录 A.3 NSSM 安装命令（`nssm install FileCortex "...\fctx-web.exe" "--host 127.0.0.1"`）；
- 附录 A.4 systemd 单元（Linux 裸机，`Restart=on-failure`，同样单进程约束写入注释）。

**拓扑 4：CI/headless**
- `fctx open . && fctx stage . <files> && fctx export . --format xml -o context.xml` 进 artifact；MCP stdio 注册给 Agent 宿主。

### 5.5 发布门禁（扩展现有 Release Gate）

1. 现有三项保留：pytest / ruff / wheel 内容检查；
2. **新增 clean-install 冒烟**（脚本 `scripts/smoke_install.sh|ps1`）：
   ```
   python -m venv /tmp/smoke && pip install dist/*.whl
   fctx open <tmp-project> && fctx stage ... && fctx export ... | diff <golden>
   (fctx-web &) && curl /api/whoami == 200 && kill
   python mcp_server.py --transport stdio < list_tools_probe   # mock 模式退出码 2 亦可判定 SDK 缺失路径
   ```
3. **新增 Docker 构建 + compose 起容器健康检查**（仅 release 分支）；
4. CI 扩展：现有 lint/test 之外加 `build` job（`python -m build` + 冒烟），Windows runner 上跑平台敏感测试（文件锁/进程终止/编码）。

### 5.6 验收标准（Definition of Done for v7.0）

- [ ] 干净 VM/容器内 `pipx install file-cortex` → `fctx-web` → 浏览器完成 open→search→stage→generate 全链路，无手册外步骤；
- [ ] `docker compose up` 一条命令得到健康的服务实例（token 鉴权生效、配置持久化卷）；
- [ ] clean-install 冒烟脚本进 CI 并阻断不合规格局；
- [ ] `FCTX_CONFIG_DIR` 生效且有测试；
- [ ] FE-1/FE-2（Medium 竞态）与 BE-1（嵌套 gitignore）修复并带回归测试；
- [ ] README 快速开始重写为拓扑导向（本机/LAN/CI 三节）。

### 5.7 六周执行计划

| 周 | 批次 | 内容 | 验收 |
|---|---|---|---|
| W1 | 修复批 R1 | FE-1、FE-2（前端 Medium 竞态，复用现有 flushNow/generation 模式）+ 回归测试 | 竞态场景手测脚本通过 |
| W2 | 修复批 R2 | BE-1 嵌套 gitignore（walk 逐目录 spec 叠加）+ BE-3/BE-4/BE-5/BE-6 顺手批 | git 语义对齐测试（构造嵌套 ignore 用例） |
| W3 | 修复批 R3 | DT-1/DT-2（预览/导出下线程，复用现有 run_in_background 模式）+ WEB-2（generate_context 异步化） | 桌面大文件操作不冻结（手动 + 线程断言） |
| W4 | 落地批 L1 | `FCTX_CONFIG_DIR` + Dockerfile/compose + 冒烟脚本 + CI build job | compose 健康检查绿 |
| W5 | 落地批 L2 | systemd/NSSM 模板、README 拓扑化重写、版本 7.0.0、CHANGELOG | 文档-参数对齐表更新 |
| W6 | 稳固批 | Low 级台账按模块清扫（FE-3..15 / DT-3..14 / BE-2 / WEB-1..4 / CN-1..4 中的速赢项） | 全量 pytest/ruff/冒烟三绿 → tag v7.0.0 |

> 与既有 ROADMAP 的关系：本计划相当于把 Phase 2（可维护性与发布工程）中"发布工程"半边提前落地，并清偿 Phase 1 途中发现的体验债；Phase 2 其余项（服务层抽取、God Object 拆分）与 Phase 3（上下文编译器）次序不变。

---

## 6. 总结

| 维度 | 评级 | 一句话 |
|---|---|---|
| 架构设计 | ★★★★☆ | 微内核 + 单向依赖 + 安全原语收口，债务是结构性的且已被识别、有清偿计划 |
| 代码质量 | ★★★★☆ | 864 测试/0 lint 错误/修复可追溯；本轮新增 41 项发现中无 High、4 项 Medium |
| 安全工程 | ★★★★★ | 注册制沙盒 + UNC/Zip/CSWSH/PID 复用等攻击面逐轮清偿，独立复核无回归 |
| 产品定位 | ★★★★☆ | 五域贯通的差异化成立；护城河在 MCP+编排，短板在打包样式与 token 精度（Phase 3） |
| 落地就绪度 | ★★★☆☆ | 功能已完整，缺发行工程最后一公里——§5 方案六周可补齐 |

---

## 附录 A. 部署工件全文

### A.1 docker/Dockerfile

```dockerfile
FROM python:3.12-slim AS build
WORKDIR /src
COPY . .
RUN pip install --no-cache-dir build && python -m build --wheel --outdir /dist

FROM python:3.12-slim
# 非 root 运行
RUN useradd -m -u 1000 cortex
ENV FCTX_CONFIG_DIR=/data \
    PYTHONUNBUFFERED=1
COPY --from=build /dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm /tmp/*.whl
RUN mkdir -p /data && chown cortex:cortex /data
USER cortex
WORKDIR /data
EXPOSE 8000
# 单 worker 是硬约束：ProgressTracker 为进程内存态
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/whoami', timeout=3).status==200 else 1)"
CMD ["python", "-m", "uvicorn", "web_app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
```

### A.2 docker-compose.yml（LAN 团队服务器）

```yaml
services:
  filecortex:
    build: { context: ., dockerfile: docker/Dockerfile }
    ports: ["8000:8000"]
    environment:
      # 非回环绑定强制 token（web_app.py main() 校验）
      FCTX_API_TOKEN: ${FCTX_API_TOKEN:?set a strong token}
      FCTX_ALLOWED_ORIGINS: "http://your-lan-host:8000"
      FCTX_PROD: "1"
    volumes:
      - fc-config:/data            # ~/.filecortex 等价物（FCTX_CONFIG_DIR）
      - /path/to/workspaces:/workspaces:ro   # 按需读写
    restart: unless-stopped
volumes:
  fc-config:
```

### A.3 Windows NSSM 服务

```powershell
nssm install FileCortex "C:\Program Files\Python312\Scripts\fctx-web.exe" "--host 127.0.0.1 --port 8000"
nssm set FileCortex AppEnvironmentExtra FCTX_API_TOKEN=<strong-token>
nssm set FileCortex AppStdout C:\filecortex\logs\out.log
nssm set FileCortex AppStderr C:\filecortex\logs\err.log
nssm start FileCortex
```

### A.4 systemd 单元（Linux 裸机）

```ini
# /etc/systemd/system/filecortex.service
[Unit]
Description=FileCortex Web (single worker: in-process progress tracker)
After=network.target

[Service]
User=filecortex
Environment=FCTX_API_TOKEN=<strong-token>
Environment=FCTX_CONFIG_DIR=/var/lib/filecortex
ExecStart=/opt/filecortex/bin/fctx-web --host 127.0.0.1 --port 8000
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
```

### A.5 clean-install 冒烟（scripts/smoke_install.sh 骨架）

```bash
#!/usr/bin/env bash
set -euo pipefail
VENV=$(mktemp -d)/venv
python -m venv "$VENV"
"$VENV/bin/pip" -q install dist/*.whl
PROJ=$(mktemp -d); echo "hello" > "$PROJ/a.txt"
"$VENV/bin/fctx" open "$PROJ" | grep -q "PROJECT REGISTERED"
"$VCTX" stage "$PROJ" a.txt
"$VCTX" export "$PROJ" --format xml | grep -q "<filecortex>"
# Web 冒烟
("$VENV/bin/fctx-web" --port 8765 &) ; sleep 3
curl -sf http://127.0.0.1:8765/api/whoami | grep -q '"status": "ok"'
pkill -f "fctx-web --port 8765" || true
echo SMOKE-OK
```

---

## 附录 B. 新发现 BUG 汇总索引

- BE-1 嵌套 gitignore（Medium）｜ BE-2 win_quote `%%`｜ BE-3 CLI export 越界写｜ BE-4 content 空查询全扫描｜ BE-5 DuplicateWorker 哨兵｜ BE-6 progress 端点无 schema｜ BE-7 atexit 累积｜ BE-8 update_project_settings 纵深
- WEB-1 Origin 端口不对称｜ WEB-2 generate_context 线程池占用（Medium）｜ WEB-3 WS token 读取源不一致｜ WEB-4 get_children IO 放大
- FE-1 refreshProject 暂存回滚竞态（Medium）｜ FE-2 openProject 不取消在途搜索（Medium）｜ FE-3 全选可见性｜ FE-4 同文件重点击丢编辑｜ FE-5 notes 无守护写｜ FE-6 假复制成功｜ FE-7 Modal 实例累积｜ FE-8 清空弹警｜ FE-9 stats 无序守卫｜ FE-10 currentFile 失同步｜ FE-11 虚拟列表行高｜ FE-12 输出 O(n) 追加｜ FE-13 菜单尺寸硬编码｜ FE-14 fetch 无超时｜ FE-15 陈旧预览
- DT-1 主线程预览读（Medium）｜ DT-2 主线程导出/扫描（Medium）｜ DT-3 不可达预览分支｜ DT-4 状态覆盖｜ DT-5 缺守护｜ DT-6 控件态泄漏｜ DT-7 跨线程 after｜ DT-8 过滤 trace 全量重建｜ DT-9 过滤视图漏复制｜ DT-10 查重模型不更新｜ DT-11 无界排空｜ DT-12 dry-run 无去抖｜ DT-13 update() 重入｜ DT-14 死样式引用
- CN-1 哨兵契约｜ CN-2 CLI excludes 来源｜ CN-3 MCP isError｜ CN-4 私有内部导出
