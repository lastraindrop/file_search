# FileCortex v6.6.0 现阶段完整工程计划

> 角色：本轮（v6.6.0）工作的完整记录 + 下一阶段的可执行计划
> 组成：§1 现状分析 → §2 本轮已完成工作台账（内容+位置+验证）→ §3 单元测试体系（现有矩阵+新增 46 项明细+后续补测计划）→ §4 下一阶段计划（批次/顺序/位置/验收）→ §5 质量门禁与发布流程
> 基线：846 passed / Ruff 0 errors / 版本 6.6.0

---

## 1. 现状分析（我们在哪里）

### 1.1 项目健康度快照

| 维度 | 状态 | 依据 |
|------|------|------|
| 功能完备性 | ★★★★☆ | 四端（Web/桌面/CLI/MCP）+ 搜索/暂存/导出/文件治理/查重全通；CLI 功能面窄于 Web |
| 安全 | ★★★★☆（本轮前 ★★★☆☆） | 9 个 P1 旁路/自杀/丢数据路径全部关闭；遗留 P2：WS 工具流无超时、token 本地注入面 |
| 正确性 | ★★★★☆ | 挂起类（as_completed CANCELLED 态、背压）与竞态类（categorize、配置锁）已修；save 编码回写等 7 项 P2 排期 |
| 可维护性 | ★★★☆☆ | 三个 God Object、四入口碎片化、按版本堆叠的测试——结构性债务未动（有意延后） |
| 可交付性 | ★★★★☆ | wheel/sdist 含资源；`python web_app.py` / `fctx` / MCP stdio 均可直接落地使用；多进程部署仍受单进程约束（进度端点进程内实现） |

### 1.2 本轮工作的方法论（为什么这样做）

1. **四路并行深度审查**（core / Web+入口 / 前端+GUI / 测试）产出原始发现 → 全部 P1 与代表性 P2 由人工源码复核确认（排除误报）；
2. **修复优先级**：安全旁路 > 数据丢失 > 挂起/竞态 > 行为不一致 > 打磨；
3. **每修必有锚**：每个修复对应至少一个回归测试（46 项新增），并为行为变更的 4 个旧测试更新断言；
4. **发现即修 bug 之外的意外收获**：复核中发现并修复了审查未完全预见的问题（`as_completed` 对 CANCELLED 态 future 永久挂起——比原报告的 CancelledError 逃逸更隐蔽，实测复现后重写收割逻辑）。

## 2. 本轮已完成工作台账（改了什么、在哪里、为何）

### 2.1 P1（安全旁路与数据完整性，9 项）

| # | 文件:位置（v6.6.0 后） | 修改内容 | 关联测试 |
|---|------------------------|----------|----------|
| 1 | `file_cortex_core/security.py` `validate_project` | 剥离长前缀后增加 `unc\` 前缀检查（大小写不敏感）；resolve 后复查 `ntpath.splitdrive` 网络盘符（防 symlink/SUBST 间接指向网络盘） | TestUncLongPrefixBypass（4 项） |
| 2 | `file_cortex_core/security.py` `is_safe` | 同上的目标侧 `unc\` 检查 | 同上 |
| 3 | `routers/project_routes.py` `/api/project/note`、`/api/project/tag` | 前置 `get_valid_project_root()` 注册闸门（此前仅包含性检查 → 自动注册任意目录） | TestNoteTagRegistrationBypass（3 项） |
| 4 | `mcp_server.py` `main()` | 转发 `transport`；`http`→`streamable-http` 别名；choices 对齐 SDK 字面量（sse/streamable-http） | TestMcpTransportWiring（3 项） |
| 5 | `file_cortex_core/actions.py` `execute_tool` | `start_new_session=(os.name != "nt")`——POSIX 下脱离服务器进程组，超时 killpg 不再自杀 | TestExecuteToolProcessGroup |
| 6 | `file_cortex_core/config.py` `save()` | 磁盘配置损坏重写前 `shutil.copy2` 备份为 `<name>.corrupt-<ts>`；备份失败也仅记日志不阻断 | TestCorruptConfigBackup |
| 7 | `static/js/main.js` `categorizeStaged` | `syncStagingToBackend` 重构为带 `flushNow()` 的调度器；categorize 后先 `await flushNow()` 再 `refreshProject()`（消除防抖写与 reload 的竞态） | （前端契约层验证；行为验证排期 Playwright） |
| 8 | `file_search.py` `on_tree_select_preview` | 未保存守卫：`_last_loaded_preview` 快照 + 脏比较 + askyesno；保存/读取路径同步维护快照 | （GUI 无行为测试层；快照逻辑为纯数据流，排期抽取测试） |
| 9 | `routers/fs_routes.py` `/api/fs/extract` + `actions.extract_archive` | UNC 源双闸（路由层字符串检查 + core 层在 resolve/exists **之前**检查——顺序关键，否则检查本身触发 SMB） | TestExtractUncSource（2 项） |

### 2.2 P2（挂起/竞态/契约，21 项）

| # | 文件:位置 | 修改内容 | 关联测试 |
|---|-----------|----------|----------|
| 10 | `search.py` 背压块 | `next(as_completed(...))` 无限阻塞 → `wait(0.1, FIRST_COMPLETED)` 分片循环 + stop 检查 | test_backpressure_responds_to_stop_event |
| 11 | `search.py` 最终收割 | 重写为「`done()` 预收割（覆盖 as_completed 永不回报的 CANCELLED 态）→ 0.2s 分片 wait → stop 检查」 | test_generator_survives_cancelled_futures |
| 12 | `search.py` 三处 `f.result()` + `SearchWorker.run` | 显式捕获 `CancelledError`（BaseException），保证 DONE 哨兵可达 | test_worker_always_emits_done |
| 13 | `file_io.py` `should_ignore` | 手动模式匹配前 `str(rel_path).replace("\\","/")`——Windows 子路径模式生效 | TestManualExcludeSubpathPatterns（3 项） |
| 14 | `file_io.py` `get_metadata` fallback | 补全 path/type/size_fmt/mtime_fmt/ext 全契约键 | TestMetadataFallbackContract（2 项） |
| 15 | `routers/ws_routes.py` `run_search` | 补 except → `{"status":"ERROR","msg":...}` 帧（与 run_stream 对齐），finally 仍发 DONE | TestWsSearchErrorNotSwallowed |
| 16 | `routers/ws_routes.py` 两处认证失败 | 先 `accept()` 再 `close(4001)`——自定义码真正可达浏览器 | TestWsAuthCloseCodeDelivery（+ 更新 test_ai_enhanced 旧行为断言） |
| 17 | `web_app.py` origin 判定 | 废弃 Host 派生的 base_url 比较；改为 origin 主机 ∈ {127.0.0.1, localhost, ::1} ∪ 显式白名单 | TestOriginHardening（3 项） |
| 18 | `web_app.py` + `ws_routes.py` token 比较 | `encode("utf-8")` 后 `compare_digest`（非 ASCII 不再 500） | test_non_ascii_token_header_returns_401_not_500 |
| 19 | `web_app.py` `create_app` | lifespan：shutdown 时 `asyncio.to_thread(_shutdown_tracked_processes)` 终止被跟踪进程并注销 | TestShutdownTrackedProcesses |
| 20 | `duplicate.py` `run` | `_cancelled()` 辅助：所有取消路径统一投递 `("DONE", False)` | TestDuplicateWorkerCancelSentinel |
| 21 | `gui/duplicate_finder.py` | ERROR 分支 set stop_event；after_id 跟踪 + on_close 取消 + winfo_exists 守卫 | （GUI 层；逻辑由 20 覆盖核心语义） |
| 22 | `gui/batch_rename.py` | 提取 `build_literal_substitution()`：simple 模式双侧转义 | TestBatchRenameLiteralReplacement（3 项，含反例文档化） |
| 23 | `gui/path_collection.py` | clipboard_append 后 `self.update()` 再 destroy | （GUI 层） |
| 24 | `static/js/main.js` `startSearch` | 空查询校验移到 `++searchGeneration` 之前（消除 UI 楔死） | （契约层） |
| 25 | `static/js/main.js` `toggleSelectAll/updateBulkUI` | 选择集合 = 树 DOM ∪ `state.searchResults`（虚拟列表全量） | （契约层） |
| 26 | `static/js/state.js` `copyToClipboard` | Secure Context 检测 + textarea/execCommand 回退；main.js 4 处调用点替换 | （契约层） |
| 27 | `static/js/main.js` `executeToolOnStaged` | `toolRunInFlight` 重入守卫；state.js 补声明 `activeToolSocket/toolRunInFlight` | （契约层） |
| 28 | `static/css/style.css` | 亮色主题 `.btn-close-white` → `invert(1)`（关闭钮不再隐形） | （样式契约） |
| 29 | `config.py` `_is_process_alive` | ACCESS_DENIED→存活；argtypes/restype 修正；`_config_file_lock` unlink 前重读 owner（TOCTOU）；fd 泄漏与 stat 二次异常加固 | （间接由并发既有回归覆盖；专项并发测试排期） |

### 2.3 P3（边界与打磨，~20 项）

| # | 位置 | 内容 |
|---|------|------|
| 30 | `search.py` SearchQuery | `max_results ge=1 le=5000`；`max_size_mb ge=0 le=4096`（0=合法的"不读内容"限） |
| 31 | `file_io.py` read_text_smart | `max_bytes<=0` → 返回 ""（防 `read(-1)` 全量读取） |
| 32 | `routers/schemas.py` | export_format→`Literal["markdown","xml"]`；tag→`max_length=200`；batch_rename count→`ge=1 le=100` |
| 33 | `fctx.py` main | 无/未知子命令 → `print_help` + `sys.exit(2)`（3 个旧测试更新断言） |
| 34 | `actions.py` extract | 校验全部通过后才 `mkdir`（拒绝不再残留空目录） |
| 35 | `routers/action_routes.py` | 超时 env 解析一次+回退 300s；跳过路径写入 results（`{"error": "Path outside project root; skipped"}`） |
| 36 | `mcp_server.py` | fmt 大小写归一化；搜索 50 条截断提示（原 off-by-one 51） |
| 37 | `config.py` get_project_data_obj | 空路径 raise ValueError（防 `projects[""]`） |
| 38 | `static/js/ui.js` | isPinned 归一化比较（`norm()`） |
| 39 | `static/js/main.js` | stopSearch 计数改用 state.searchResults；copyPath `data-orig-label`+clearTimeout |
| 40 | `static/js/api.js` | 422 detail 数组 → 可读消息串 |
| 41 | `templates/index.html` | bulkActions 常显 + `#bulkActionButtons` 禁用态（全选零选中可达）；契约测试同步更新 |

### 2.4 文档与版本同步

- 版本：`__init__.py` / `pyproject.toml` / README ×2 / 参数表 → **6.6.0**
- 测试计数：`test_packaging.EXPECTED_TEST_COUNT=846`；README 头条与表格（新增 v6.6.0 行 46 项）
- ROADMAP 新增 "Delivered in 6.6.0" 全清单 + 里程碑表；CURRENT_ENGINEERING_PLAN 基线与 v6.6.0 段落
- 新增 `docs/` 四份报告（本文件 + ARCHITECTURE_REVIEW + POSITIONING_ANALYSIS + CODE_REVIEW_V660）

## 3. 单元检测体系（细致而全方位的验证）

### 3.1 现有矩阵（846 项的分布）

| 层 | 文件数 | 项数 | 覆盖 |
|----|--------|------|------|
| 内核（security/config/file_io/search/context/duplicate/actions） | 12 | ~380 | 路径矩阵 15 场景、三方合并、并发 save 10-20 线程、zip-slip 12 载荷、回滚注入、池自愈 |
| Web API + WS | 4 | ~150 | 35 条路由、CORS/Auth/CSP、token、协议 DONE/ERROR |
| 前端契约 | 1 | 43 | HTML/JS/CSS 字符串契约、SRI、CSP |
| CLI / MCP / 打包 | 5 | ~90 | 9 子命令、磁盘级 reload、打包一致性、版本三处一致 |
| v6.6.0 回归（新） | 1 | **46** | 见 3.2 |

### 3.2 新增 46 项明细（tests/test_v660_review_fixes.py）

| 类 | 项数 | 验证目标 | 关键断言设计 |
|----|------|----------|--------------|
| TestUncLongPrefixBypass | 4 | UNC 长前缀双路径拦截 | win32 下 PermissionError("UNC")；is_safe=False；POSIX skip 显式声明 |
| TestNoteTagRegistrationBypass | 3 | 注册闸门 | 403 + `dm.config.projects` **不含**未注册路径（防旁路的直接证据）；注册后 200 |
| TestExtractUncSource | 2 | UNC 源双闸 | core 层 PermissionError；路由层 403 |
| TestMcpTransportWiring | 3 | transport 转发 | FakeServer 捕获 run() kwargs：stdio={}，http→streamable-http+host/port |
| TestExecuteToolProcessGroup | 1 | 进程组脱离 | patch Popen 捕获 kwargs，断言 `start_new_session is (os.name!="nt")` |
| TestShutdownTrackedProcesses | 1 | 生命周期清理 | 存活→terminate+注销；已退出→仅注销 |
| TestCorruptConfigBackup | 1 | 备份先行 | glob `*.corrupt-*` 存在且内容逐字节等于原垃圾数据 |
| TestProjectDataObjGuard | 2 | 空键防御 | ""/None → ValueError("empty") |
| TestSearchCancelledFuture | 3 | 挂起修复 | 预取消 future 生成器正常终止（旧代码此处**无限挂起**，实测复现）；worker 哨兵必达；背压 10s 内响应 stop（线程 join 断言） |
| TestManualExcludeSubpathPatterns | 3 | Windows 模式 | should_ignore 两级模式 + walk_filtered 集成（排除 src/* 且保留 config.json） |
| TestMetadataFallbackContract | 2 | 降级契约 | 9 键全集 + ws_routes 逐键下标复现（防回归） |
| TestWsSearchErrorNotSwallowed | 1 | ERROR 帧 | monkeypatch 搜索抛 RuntimeError → 客户端先收 ERROR(msg 含原因) 再收 DONE |
| TestDuplicateWorkerCancelSentinel | 1 | 哨兵契约 | 预设 stop → 队列必含 ("DONE",*) |
| TestOriginHardening | 3 | Host 伪造 | evil.example 双头伪造→403；localhost:8123→200；latin-1 字节 token→401（httpx 层面复现真实攻击面） |
| TestWsAuthCloseCodeDelivery | 1 | 关闭码交付 | WebSocketDisconnect.code==4001（更新旧断言"accept 前关闭"为正确行为） |
| TestSchemaBounds | 3 | 422 边界 | "XML"→422；201 字符 tag→422；count=0→422 |
| TestSearchQueryBounds | 3 | 模型边界 | 0/-1 拒绝；max_size_mb=0 合法（既有"跳过读文件"语义的兼容锚） |
| TestReadTextSmartNegativeGuard | 1 | 负限防御 | -5 → ""（旧代码返回全文） |
| TestCliExitCode | 1 | 退出码 | 子进程真实运行 rc==2 |
| TestExtractDirHygiene | 1 | 目录卫生 | FileNotFoundError 且 dst 不存在 |
| TestMcpPolish | 2 | fmt/截断 | " XML "≡xml；60 文件→"truncated" |
| TestBatchRenameLiteralReplacement | 3 | 字面替换 | 双侧转义不抛 bad escape 不注入 \n；含反例文档化测试（证明旧缺陷真实存在） |
| TestExecuteTimeoutParsing | 1 | env 容错 | 垃圾 env + mock 进程 → 200 + exit_code=0（旧代码落入 "failed to start"） |

**测试设计原则**（延续并强化既有纪律）：
- 断言**结果状态**而非实现细节（如注册旁路直接断言 projects 集合内容）；
- 反例文档化：保留一个"旧行为确实错误"的证明测试（test_unescaped_control_sequence_would_be_wrong）；
- 平台差异显式 skipif，不静默缩水；
- 挂起类测试自带线程 join 超时断言，flaky 即失败（fail-fast）。

### 3.3 后续补测计划（Phase 2 批次内执行）

| 优先 | 目标 | 用例设计 | 位置（拟） |
|------|------|----------|-----------|
| P0 | `/api/fs/move`、`/api/fs/delete` happy path | 复用 project_client：move 2 文件→断言新位置存在+旧位置消失+staging 不变 | tests/test_web_api.py 扩展 |
| P0 | WS 工具流超时（随修复） | mock 慢进程 + FCTX_EXEC_TIMEOUT=1 → 断言超时帧与进程终止 | tests/test_v660_review_fixes.py 扩展 |
| P1 | 配置锁并发（TOCTOU 修复） | 双进程 multiprocessing 各自 save 100 次 → 最终文件可解析且双方写入均存在 | tests/test_dm_config.py 扩展 |
| P1 | 四入口策略一致性 | 同一 fixture 下 WS/CLI/MCP 搜索结果集相等（excludes 组合统一后） | tests/test_parity.py（新） |
| P1 | Playwright 冒烟 | open→search→stage→generate 一条链 + 破坏性操作确认弹窗 | e2e/（新目录，标记 `@slow`） |
| P2 | GUI 纯逻辑抽取 | `build_literal_substitution` 模式推广：预览脏检测、树过滤谓词抽为可测函数 | tests/test_gui_logic.py（新） |
| P2 | 既有 8 个自证用例改造 | CDATA/relative_to/env 组用例改为真实产品路径或删除；40 组重名合并 | 对应历史文件 |

## 4. 下一阶段计划（顺序、内容、位置、验收）

> 原则延续 CURRENT_ENGINEERING_PLAN：不做"又一次全面稳定化重写"，做**有验收点的增量批次**。

### 批次 2.0：残留 P2 收尾（预计 1 个迭代）

| 顺序 | 位置 | 修改 | 验收/测试 |
|------|------|------|-----------|
| 1 | `routers/ws_routes.py` websocket_action_stream | 工具流接入 `FCTX_EXEC_TIMEOUT`（对齐 HTTP 版）；超时后 terminate+注销 | 新 WS 超时测试（§3.3 P0） |
| 2 | `file_cortex_core/actions.py` stream_tool | Windows：Job Object（或 `taskkill /T /F` 兜底）；POSIX：start_new_session+killpg；`exit_code` 帧必达 | mock 孙进程持有管道→断言不无限阻塞 |
| 3 | `file_cortex_core/config.py` save 风暴 | 脏标记 + 500ms 去抖合并写；`DataManager.data` 属性淘汰计划（deprecation） | 100 次 add_note → 磁盘写 ≤2 次的计数断言 |
| 4 | `file_search.py` copy_all_staging_content / staging trace | 后台线程 + after 回主线程渲染（复用统计线程模式 H4） | （GUI 逻辑抽取后可测） |
| 5 | `web_app.py` index token 注入 | 改一次性 ticket（首次 GET / 签发短时 token）或仅显式 `--inject-token` 开启 | 转发场景下页面不含真实 token 的断言 |
| 6 | `fctx.py` | `unstage`/`delete`/`move` 子命令；excludes 组合= 项目配置 ∪ CLI 参数 | CLI 新命令磁盘级 reload 断言 |
| 7 | `mcp_server.py` `_ensure_tool_registry` | 注册失败改为硬失败（fail-fast）+ 启动自检报告真实注册状态 | mock 注册异常→server 拒绝启动的测试 |

### 批次 2.1：结构重构（预计 2 个迭代，行为保持）

| 顺序 | 位置 | 修改 | 保护网 |
|------|------|------|--------|
| 1 | `routers/` | 统一授权依赖 `verify_registered_path()`（A1 结构性结论）；全路由替换 | 既有 35 路由行为测试全绿即重构安全证明 |
| 2 | `file_cortex_core/config.py` | 拆 `ConfigStore`（IO/锁/合并）+ `ProjectService`（域逻辑）；`get_project_data_obj` 读写分离 | 并发 save/合并既有回归 |
| 3 | `file_cortex_core/` | 新增 `logging_setup.py`，config.py 去日志职责 | import 副作用测试（无 ~/.filecortex 创建） |
| 4 | `static/js/main.js` | 拆 search.js / tools.js / progress.js；消除 `...api,...ui` 展开遮蔽 | 前端契约测试 + Playwright |
| 5 | `file_search.py` | 按 Search/Tree/Staging/Preview/Tools 拆 controller；poller 链取消 | GUI 纯逻辑抽取测试 |
| 6 | `tests/` | 重组为 unit/integration/contract 三层 + marker（slow/windows）；修 README 无效指令 | EXPECTED_TEST_COUNT 守卫继续生效 |

### 批次 2.2：发布工程（与 2.1 并行）

- `.github/workflows/`：Windows+macOS+Linux 矩阵（pytest + ruff + `python -m build` + wheel clean-install 冒烟）
- Playwright E2E 入仓（`@slow` marker 本地默认跳过）
- `build_exe.py`：补 web/fctx console 入口或 README 明示产物范围

### 批次 3.x：上下文编译器（对齐 ROADMAP Phase 3，学 Repomix/Aider）

1. JSON manifest（path/hash/size/tokens/truncation/reason）+ 确定性 recipe → `context.py` 新模块 `manifest.py`
2. 精确 tokenizer（tiktoken 可选依赖）+ 硬预算
3. tree-sitter 符号图（可选依赖，降级 ASCII 树）→ 蓝图升级
4. git diff 感知排序；secret 扫描报告（regex 规则集起步）
5. **语义决策**：regex+content 组合模式（解决 search.py:193 不可达分支）→ 先文档化后实现

### 批次 4.x：索引与受审视整理（维持非目标边界）

- SQLite/FTS5 增量索引（schema 迁移前先出 ADR）
- 规则优先分类计划：dry-run → 冲突预览 → 批准 → 审计 → undo（学 Hazel，模型仅建议）

## 5. 质量门禁与发布流程（每批次必须全绿）

```bash
python -m pytest -q                 # 846 项全过（新增测试同步 EXPECTED_TEST_COUNT 与两份 README）
python -m ruff check .              # 0 errors
python fctx.py projects             # CLI 冒烟
python -c "from fastapi.testclient import TestClient; from web_app import app; TestClient(app).get('/')"   # Web 冒烟
python -m build --no-isolation      # wheel 检查 templates/static/gui
```

发布前核对：版本四处一致（core/pyproject/README×2）、测试计数三处一致（packaging 常量/README×2）、`git diff --check`、完整 staged diff 复核。

---

## 附：本轮工作验证记录

| 验证项 | 结果 |
|--------|------|
| 新增测试单文件 | 46 passed（含挂起类 fail-fast 断言） |
| 全量套件 | 845 passed → 修正最后 1 个旧断言后 **846 passed, 0 failed**（328s，Windows） |
| Ruff | 0 errors（新增代码 Google Style 全项：docstring/D/SIM/I 规则齐过） |
| CLI 冒烟 | `fctx.py projects` 正常列示 |
| Web 冒烟 | `GET /` 200；`GET /api/whoami` 200 `{"version":"6.6.0"}` |
| 行为变更清单 | WS 4001 交付方式、CLI 无命令退出码、bulkActions 常显、MCP 截断提示——均有测试锚定与文档记录 |
