# FileCortex v6.6.1 完整 Code Review 报告

> 方法：核心库逐行精读 + 三路并行深度审查（Web 层 / 桌面+CLI+MCP 入口 / 前端）+ 全部发现的人工源码复核（含实测复现）
> 级别定义：P1=安全旁路或功能锁死；P2=用户可感知的功能缺陷；P3=打磨项
> 标记：✅=本轮已修复并附回归测试（tests/test_v661_review_fixes.py，18 项）；⏳=已排期（见 IMPLEMENTATION_PLAN_V660.md §4）；ℹ️=设计取舍/记录在案；❌=复核后否决（误报）
> 基线：6.6.0（49f107b，846 passed）→ 本轮：864 passed / Ruff 0 errors / 版本 6.6.1

---

## 1. Web 层（web_app.py + routers/）

| 级别 | 位置 | 问题 | 状态 |
|------|------|------|------|
| P1 | ws_routes.py 两端点 | WS 完全无 Origin 校验：HTTP 中间件只处理 `scope["type"]=="http"` 且仅覆盖 `/api/`，浏览器 WS 又不受同源策略约束——恶意网页可经 `/ws/search` 读取已注册项目内容、经 `/ws/actions/execute` 执行工具命令（CSWSH） | ✅ `_ws_handshake_allowed()`：token + Origin 双检（无 Origin 的非浏览器客户端放行；回环主机/显式白名单放行；其余 accept 后 close(4001)，与既有 token 拒绝模式一致） |
| P2 | ws_routes.py / action_routes.py execute | `get_project_data(原始路径)` 以客户端原始输入查询——`get_project_data_obj` 的 create-if-missing 语义使子目录输入凭空注册幽灵项目条目（可持久化），且工具模板解析到该条目的默认值而非父项目实际配置 | ✅ 改用 `get_valid_project_root()` 解析后的根查询 |
| P2 | ws_routes.py finally | 工具流成功结束后仍对已退出 PID 无条件 `terminate_process`（taskkill）：每次成功执行白白派生 taskkill 子进程，且存在 PID 复用误杀无关进程树的窗口（HTTP 侧 BUG-W6 有 `poll()`+归属校验，WS 清理路径没有） | ✅ 成功路径 `current_pid[0] = None`；断连/异常路径照常终止 |
| P2 | ws_routes.py enqueue ×2 | 背压重试竞态：`future.result(timeout=0.1)` 超时后 `future.cancel()` 不查返回值——put 恰在超时判定后完成时，条目已入队而重试再放一次 → 客户端收到重复结果帧 | ✅ `cancel()` 返回 False 即视为已入队（返回 True） |
| P3 | web_app.py verify_api_token | `_is_wildcard_origin` 冗余前半句；`origin not in ALLOWED_ORIGINS` 条件被 same_origin 包含；`import hmac` 在每请求热路径内 | ✅ 提取 `_origin_allowed()` 单源辅助（WS 复用同一策略），条件化简，hmac 移至模块顶部 |
| P3 | services.py / fs_routes.py | `get_project_config_for_path` 双重 `dm = dm or get_dm()`；`norm_path(p.parent) if p.parent else None` 恒真分支；`getattr(req,'project_path',None)` 多余防御 | ✅ 清理 |
| P3 | schemas.py | `GlobalSettingsRequest.settings/theme/allowed_extensions` 无大小界限（与 BUG-W9 其余字段加固不一致）；`_validate_dict_size` 错误消息把字符数当字节数 | ✅ settings 挂 100KB 校验、theme 64、allowed_extensions 10k；消息修正 |
| P3 | ws_routes.py 两处 enqueue 逐字重复 | 握手拒绝流程同样重复 | ✅ 提取 `_make_enqueue()` 工厂；握手合并为 `_ws_handshake_allowed()` |
| ℹ️ | web_app.py 回环 Origin 任意端口放行 | 看似 CSRF 缺口，实为 `test_local_port_origin_allowed` 明确固化的开发工作流（"Any loopback host/port origin stays allowed"） | ℹ️ 维持设计；网络部署以 token + 显式白名单为界 |
| ❌ | index.html bootstrap SRI | 审查子代理报告哈希 `j+68` 错误（critical）；实测下载比对文件内为 `j/68` 且与 CDN 实测哈希逐字节一致 | ❌ 误报，不改 |

## 2. 前端（static/ + templates/）

| 级别 | 位置 | 问题 | 状态 |
|------|------|------|------|
| P1 | main.js runNext | 工具流不处理后端 `{"status":"ERROR","msg":...}` 帧，且无 `socket.onclose`——鉴权拒绝（close 4001）或服务端错误时 Promise 永挂 → `toolRunInFlight` 永真，工具功能锁死到刷新页面 | ✅ ERROR 帧纳入终态 + onclose 兜底 resolve（模态关闭取消路径同样解锁） |
| P1 | events.js + main.js toggleSelectAll | click 委托先无参调用 `toggleSelectAll(undefined)`：清空选择集并把所有 DOM 复选框置 false，随后的 change 事件读到 false——**"全选"永远变成"全部取消"** | ✅ click 阶段跳过 checkbox/SELECT，由 change 驱动（favGroupSelect/pathProfileSelect 的 click 重建 options 问题一并修复） |
| P2 | main.js startSearch onclose | 服务器静默关闭（典型：close 4001 无任何消息帧）时 onclose 只清引用——骨架 "Searching..." 与 count '...' 永久滞留 | ✅ `completed` 标志 + onclose 兜底渲染断连态 |
| P2 | api.js _fetch | `res.json()` 失败后 catch 内 `res.text()` 抛 "body stream already read"，真实错误（如反代 502 HTML 页）被掩盖 | ✅ 先 `text()` 一次再 `JSON.parse` |
| P2 | main.js openProject | 无 generation 守卫：快速连点两个工作区，`api.openProject` / `fetchProjectConfig` / `loadWorkspaces` 交错完成，A 的 projConfig 可嫁接到 B 的树上（previewFile 已有同型防护，此处缺失） | ✅ `openProjectSeq` 代际守卫 |
| P2 | main.js terminateProcess | 后端对未知/复用 PID 返回 200 + `{"status":"error","msg":...}`，前端只查 HTTP 状态码恒显示 "Termination signal sent" | ✅ api.terminateProcess 改 `_postJson`；UI 按 status 分支 |
| P3 | main.js archiveStaging | 模板 value 插值未过 `escapeHtml`（同文件其余 modal 均转义）——当前值为常量无害，属防御缺口 | ✅ 补转义 |
| P3 | main.js toggleFavorite | `projConfig.groups[group]` 无 groups 键防御（异常配置 TypeError → 误导性 toast） | ✅ 补防御 |
| P3 | main.js / api.js / state.js / ui.js | 死代码：`loadTreeChildren` 无意义 rethrow；`saveProjectTools`/`saveProjectCategories` 及对应 endpoints 无调用者；`ui.renderSearchResultItem` 有害存根（被误用会以单条覆盖整个虚拟列表） | ✅ 移除 |

## 3. 桌面版（file_search.py）

| 级别 | 位置 | 问题 | 状态 |
|------|------|------|------|
| P1 | _init_context_menu | 对四树统一 `bind("<Button-3>")`——Tk bind 是**替换**语义，`_init_staging_tab` 先绑定的专用菜单被顶掉，"移除当前过滤出的所有文件" 永久不可达（死功能） | ✅ 循环剔除 `tree_staging`，专用菜单恢复 |
| P2 | _perform_search / process_queue | ① 每次触发直接 `process_queue()` 启动新轮询链，旧链不取消——快速切换模式/复选框积累并行循环争抢同一队列、状态文本互覆；② TOCTOU：`get_nowait()` 抛 Empty 与 `is_alive()` 判定之间 worker 恰好 put DONE 并退出 → 哨兵永不被消费，状态栏卡死 "扫描中..." | ✅ `_poll_after_id` 单链管理（新搜索前 cancel）+ "线程已死但队列非空则继续轮询" 守卫 + 终态兜底 |
| P2 | execute_tool_on_paths | 工具执行线程无并发防护：连点按钮对同一批文件并行跑外部命令；与 Web 端 `toolRunInFlight` 守卫不对称 | ✅ `_tool_run_in_flight` in-flight 守卫 |
| P2 | _run_stats_calc_thread | 统计线程 `read_text_smart(p)` 无字节上限——清单含百 MB 日志时仅为估算 token 整体读入内存 | ✅ 1MB 采样 + 按文件大小比例外推 |
| P3 | show_status | after 计时器堆积：连续消息时旧定时器提前把新消息的红色恢复为灰色 | ✅ `_status_after_id` 取消重建 |
| P3 | 模块顶部 | `TOKEN_RATIO` 死常量（估算走 FormatUtils 加权算法） | ✅ 移除 |
| ⏳ | ctx_copy_file_to_os | 主线程同步 `subprocess.run(powershell)`（冷启动 1-3s UI 冻结）——后台化排期批次 2.0（附录 A #4a） | ⏳ |
| ⏳ | on_close_window | 工具子进程不随窗体关闭终止（桌面版无 ProcessManager 等价物）——排期批次 2.0（附录 A #4b）与 Web lifespan 模式对齐 | ⏳ |
| ℹ️ | 桌面其余项 | L1 BatchRenameWindow None 守卫（gui 导入失败时真实可达，保留）；trigger_search 纯转发（7 处绑定，改动不值）；预览主线程同步读（网络盘可感知卡顿，随批次 2.0 后台化） | ℹ️ |

## 4. CLI / MCP（fctx.py / mcp_server.py）

| 级别 | 位置 | 问题 | 状态 |
|------|------|------|------|
| P2 | fctx.py main | 重定向/管道下 stdout 回落 ANSI 代码页（GBK）：工具输出/结果中的 emoji 等触发 UnicodeEncodeError，`fctx ... \| findstr` 直接崩溃 | ✅ `_guard_output_encoding()`：`reconfigure(errors="replace")`（实测：无守卫 exit=1 → 有守卫 exit=0） |
| P2 | fctx.py cmd_search | `relative_to(proj_root)` 两端形态必不匹配（proj_root 为 norm_path 小写正斜杠，结果路径为原生 resolve）——"相对路径显示" 在 Windows 上 100% 失效 | ✅ 归一化后 PurePosixPath 比较（实测输出 `src/main.py`） |
| P2 | fctx.py cmd_stage/copy/extract | 相对路径先 `norm_path`（内部 abspath）锚定到 **CWD**——项目外执行 `fctx stage <proj> src/main.py` 报 "outside project root"；dst_dir help 明言 "relative to project root" 而实现同病 | ✅ `_resolve_in_project()` 锚定项目根（三处统一） |
| P3 | fctx.py cmd_run | 工具执行失败（error 帧）仅打印仍 exit 0——CI/脚本无法感知 | ✅ 失败翻转返回值 |
| P3 | fctx.py --limit | 无校验：`--limit 0` 打印 0 条但 "Total: N"；负数切片语义异常 | ✅ `max(1, limit)` 夹取 |
| P2 | mcp_server.py 三个工具 | `get_file_context`/`get_project_blueprint`/`get_file_stats` 为 async 却同步执行磁盘 I/O——冻结 stdio 心跳与其他工具（search_files 已有 to_thread 先例，其余未跟上） | ✅ 统一 `asyncio.to_thread` 包裹 |
| P3 | mcp_server.py search_files docstring | 描述漏报 `content` 模式——工具描述是 LLM 选参依据 | ✅ 补全 |

## 5. 测试体系（本轮新发现）

| 级别 | 位置 | 问题 | 状态 |
|------|------|------|------|
| P2 | tests/conftest.py | CLI/MCP 入口测试（如 `test_cli_open_existing_path`、`test_fctx_open_does_not_show_help`、`test_mcp_register_duplicate_workspace`）直接调用 `fctx.main()`/注册函数而未 patch `_CONFIG_FILE`——**把 pytest 临时目录写进开发者真实 `~/.filecortex/config.json`**（实测发现：`fctx projects` 列出多个指向已删除临时目录的残留条目） | ✅ conftest 新增 autouse `_isolated_config_file` 夹具：全部测试默认隔离到 tmp 配置；自带路径管理的测试（clean_config/api_client/显式 patch）嵌套覆盖不受影响 + `test_cli_open_writes_isolated_config` 锚 |

## 6. 未修复/记录在案（延续既有排期）

- WS 工具流无执行超时（HTTP 有 `FCTX_EXEC_TIMEOUT`）——批次 2.0 #1（既有）。
- `stream_tool` 孙进程泄漏——批次 2.0 #2（既有）。
- 桌面主线程 I/O（预览/导出/PowerShell 剪贴板）——批次 2.0 #4（本轮扩充为 4a/4b，见附录 A）。
- `win_quote` 对交互 cmd 的 `%`/引号语义——actions.py 审查项（既有 ⏳ Phase 2；Windows 文件名字符集缓解）。
- enqueue 重复入队竞态的确定性测试难以稳定构造（已修未锚，行为由背压既有回归覆盖）。
- 桌面版四个 P2 修复无 GUI 行为测试层——以源码契约测试锚定（TestReviewFixSourceContracts），行为测试随批次 2.1 GUI 逻辑抽取补齐。

## 7. 本轮验证记录

| 验证项 | 结果 |
|--------|------|
| 新增回归 | 18 passed（tests/test_v661_review_fixes.py） |
| 全量套件 | 864 passed, 0 failed（Windows） |
| Ruff | 0 errors |
| JS 语法 | node --check × 5 文件全过 |
| WS Origin 实测 | 外来 Origin → close(4001)；回环/无 Origin → 放行 |
| CLI 实测 | 项目外 CWD 相对路径 stage 成功；搜索输出相对路径；管道 exit=0 |
| 编码守卫实测 | GBK 管道下 emoji：无守卫 exit=1 → 有守卫 exit=0 |
| 版本/计数一致性 | pyproject = core = README×2 = 6.6.1 / 864，由 test_packaging 守卫验证 |
| 行数 | 生产代码净增 ~140 行（含防回归注释；死代码删除对冲） |
