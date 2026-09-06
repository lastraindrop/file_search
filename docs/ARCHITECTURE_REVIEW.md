# FileCortex v6.6.0 架构审查报告

> 审查范围：全仓库（core 14 模块 / routers 8 模块 / 前端 7 模块 / 4 个入口 / 27 个测试文件）
> 审查方法：4 个并行深度审查（core 内核 / Web 层与入口 / 前端与桌面 GUI / 测试体系）+ 人工复核全部 P1 级发现
> 基线：v6.5.3 (0537cac)，800 tests / Ruff 0 errors
> 结论摘要：架构分层清晰、无循环依赖、安全原语单点质量高；主要债务在于安全检查的"分布性"（靠每条路由记得调用，而非统一依赖）、God Object 化的 `DataManager`/`file_search.py`/`main.js`，以及四入口行为碎片化。本轮已修复全部 P1 与多数 P2（见 §6）。

---

## 1. 系统全景

### 1.1 分层架构

```text
入口层   file_search.py(Tk)  web_app.py(FastAPI)  fctx.py(CLI)  mcp_server.py(MCP)
              │                    │                    │              │
              ├────────────┬───────┴──────────┬─────────┴──────────────┤
适配层        │       routers/{project,fs,action,ws}_routes + services + schemas + common
              │       (HTTP/WS 端点、参数校验、进程注册表)
              ├────────────┬──────────────────┴───────────────────────┤
领域层        file_cortex_core/
              ├── security.py      路径安全原语 (PathValidator)     ← 零依赖根
              ├── config.py        配置 SSOT (DataManager, 文件锁, 三方合并, 日志)
              ├── file_io.py       遍历/过滤/编码探测/元数据 (FileUtils)
              ├── format_utils.py  纯格式化 (FormatUtils)
              ├── search.py        多模式搜索 (search_generator/SearchWorker/共享池)
              ├── context.py       AI 上下文导出 (ContextFormatter, OOM 保护)
              ├── duplicate.py     SHA256 查重 (DuplicateWorker)
              ├── actions.py       文件操作/工具执行 (FileOps/ActionBridge/ProgressTracker)
              ├── process_utils.py 跨平台进程终止
              └── gui/             Tk 子窗口 (batch_rename/duplicate_finder/path_collection)
              │
资源层   本地文件系统 + ~/.filecortex/config.json (唯一持久化)
```

### 1.2 依赖方向（已验证无环）

```
security → (无)
config → security
file_io → config, format_utils
context / search / duplicate → config, file_io
actions → config, file_io, security, (延迟) process_utils
gui/* → 上述各模块
routers/* → core 全部公开符号（直接内联调用，无独立领域服务层）
```

唯一的"延迟导入规避环"（actions→process_utils）实际不构成环，属过度防御；`gui/duplicate_finder` 的延迟导入同理无害。

---

## 2. 架构优点（值得保持）

| # | 优点 | 证据 |
|---|------|------|
| 1 | **微内核 + 单向依赖**：core 不依赖任何入口/框架（FastAPI 仅在 routers 出现），四入口全部复用同一内核 | `file_cortex_core/` 无 fastapi import；Tk/CLI/MCP 直接调 core |
| 2 | **安全原语单点收口**：`PathValidator.is_safe` 处理 Windows/POSIX 双语义、长前缀剥离、symlink resolve、边界前缀比较，质量高于多数同类项目 | security.py:37-106 |
| 3 | **配置持久化协议完整**：类级 RLock + 跨进程锁文件（owner+心跳）+ 三方合并 + 临时文件 + `os.replace` 原子替换 + 重试 | config.py:448-504 |
| 4 | **事务性文件操作**：extract 三阶段（校验→staging→提交+回滚）、批量 copy 回滚、zip 炸弹四重限制（成员数/单成员/总量/压缩比） | actions.py extract_archive |
| 5 | **测试纪律**：按修复批次归档回归锚点、文档-计数守卫测试（防漂移）、Windows 文件锁同步、conftest 进程清道夫 | tests/（846 项） |
| 6 | **前端竞态防护**：`previewRequestId` + `searchGeneration` 双保险、虚拟滚动、事件委托、SRI 锁定 CDN | static/js/main.js |
| 7 | **多轮加固痕迹可追溯**：代码内 BUG-W*/B*/C*/L*/H* 系列修复注释与测试一一对应 | 全仓库 |

---

## 3. 架构问题（按严重度）

### A1【结构性·高】安全检查是"分布式的"，缺乏统一授权依赖
- **现象**：`get_valid_project_root + is_path_safe` 的组合在 ≥12 个端点中手工重复，模式略有差异；`/api/project/note`、`/api/project/tag` 漏掉注册校验，`/api/fs/extract` 漏掉 zip_path 校验——三者皆是本轮 P1/P2 漏洞的直接成因。
- **根因**：routers 层没有领域服务层（services.py 仅 5 个辅助函数），授权语义靠"每条路由记得写"。
- **建议**：引入 `verify_registered_path()` FastAPI 依赖（或中间件级统一守卫），一条通路覆盖所有路径参数；`get_project_data_obj` 拆分"只读"与"读或建"两个方法，注册仅经 `validate_project`。
- **本轮处置**：已修复 note/tag/extract 三处旁路（见 §6）；统一依赖列为 Phase 2 重构项。

### A2【结构性·中】三个 God Object
| 对象 | 规模 | 混合职责 |
|------|------|----------|
| `DataManager` (config.py) | ~20 公有方法 | 单例工厂 + 仓储(锁/合并/持久化) + 工作区注册 + 笔记/标签/分组/会话域服务 + 全局设置 |
| `FileCortexApp` (file_search.py) | ~2000 行 70+ 方法 | 9 类职责：窗口构建/搜索编排/树/预览编辑/Staging/工具执行/上下文菜单/持久化/统计 |
| `App` (main.js) | ~1600 行 | 搜索 + 工具流 + 进度轮询 + 全部业务动作，且 `...api, ...ui` 展开产生同名遮蔽风险 |

- **建议**：`DataManager` 拆为 `ConfigStore`(IO/锁) + `ProjectService`(域)；桌面按 Search/Tree/Staging/Preview/Tools 拆 controller+view；main.js 拆 search.js/tools.js/progress.js（与 ROADMAP Phase 2 一致）。

### A3【横切·中】日志与副作用内嵌于 config.py
`import file_cortex_core` 即创建 `~/.filecortex/logs` 目录（config.py 初始化 logger）；日志应独立 `logging_setup.py`。同理 search.py 的模块级共享池构造也是 import 副作用（虽有 atexit 兜底）。

### A4【一致性·中】四入口行为碎片化（实测矩阵）
| 维度 | Web | Desktop | CLI | MCP |
|------|-----|---------|-----|-----|
| 搜索 excludes 来源 | 仅项目配置 | 项目配置+可编辑 | 仅 `--excludes` | 仅工具参数 |
| max_search_size 回退 | 10 | 5 | 10 | 10 |
| 结果上限 | 流式 5000 | 5000 | 5000 | 硬截 50（现已提示） |
| 不安全路径处置 | 报告(新)/静默 | 过滤+日志 | 打印 SKIPPING | 静默/警告 |
| 工具超时 | 300s | 300s | 300s | — |
| 错误呈现 | 3 种 envelope | Tk 对话框 | stderr+退出码 | 字符串 |
- **建议**：把 excludes 组合、上限、错误处置抽成 core 层共享策略对象（Phase 2）。

### A5【契约·低】队列哨兵与 API 形状未类型化
搜索/查重结果与 `("DONE",...)`/`("ERROR",...)` 元组哨兵混在同一队列，消费方靠 `isinstance` 判别；HTTP 端点零 `response_model`（仅 1 处例外），OpenAPI 退化。建议 TypedDict/dataclass 哨兵 + 逐步补 response_model。

### A6【DI·低】"名义注入、事实全局"
`get_dm()` 返回进程级单例；core 内 `FileOps.batch_categorize`、`services.get_valid_project_root` 在 dm=None 时隐式拉单例——测试想替换 DataManager 时任何漏传路径都悄悄回到全局。`ACTIVE_PROCESSES` 再导出私有 dict 本体，绕过 ProcessManager 容量/锁语义。

### A7【性能·低】IO 放大模式
- 路径模式搜索对全树每个文件先 `get_metadata`(resolve+stat) 再判断命中（应命中后取）；
- 同一文件被 `is_binary`(8KB)+`_detect_encoding`(64KB)+`read_text_smart`(全量) 打开三次；
- 每次 `add_note/add_tag` 等小改动触发完整"锁+读盘+合并+写临时+replace"协议（建议脏标记+去抖）；
- `DataManager.data` 属性每次深拷贝整配置。

---

## 4. 线程/并发模型评估

| 机制 | 结论 |
|------|------|
| DataManager 类级 RLock | 进程内真互斥，锁序一致无死锁 ✓ |
| 跨进程文件锁 | 设计正确；v6.5.3 前有两处竞态（陈旧锁 TOCTOU 误删、OpenProcess 拒绝访问误判死）——**本轮已修**（重读 owner + ACCESS_DENIED=存活） |
| SHARED_SEARCH_POOL | 多搜索并发共享安全；reinit 竞态会取消在途 future → CancelledError 逃逸 `except Exception`——**本轮已修**（显式捕获 + 最终收割处理 CANCELLED 态） |
| 背压 | 有界（40/搜索）✓；但旧实现 `next(as_completed(...))` 无限阻塞且不查 stop——**本轮已修**（0.1s 分片 wait） |
| ProgressTracker | 全读写经锁，TTL monotonic，无问题 ✓ |
| Tk 线程模型 | worker 线程 + queue + after 轮询，模式正确；残留：poller 链增殖、主线程同步 IO（导出/保存/过滤 trace）|
| WebSocket | run_coroutine_threadsafe+0.1s 超时重试的双 TimeoutError 处理（Py3.10 兼容）质量好 ✓；工具流无超时（Phase 2 待办）|

## 5. 测试体系评估

- **强度**：安全路径（zip-slip 断言磁盘零残留、磁盘级 reload 断言）达到优秀水准；文档-计数守卫防漂移是亮点。
- **结构债务**：按版本堆叠（26→27 文件）导致 ~40 组重名用例；~8 个"测试 Python 标准库"的自证用例；源码字符串断言（实现细节级）混入行为测试。
- **盲区**：Tk GUI 零行为测试（仅 1 个纯函数）；前端无执行级测试（全部为字符串契约）；`POST /api/actions/execute`（**本轮已补**）、`/api/fs/move|delete` happy path、MCP 传输层、多客户端并发 WS 为真空。
- **速度**：Windows 每 0.2s 锁等待 ×846 ≈ 170s 结构性成本，可通过按 marker 收窄。

## 6. 本轮（v6.6.0）已完成的修复对照

| 级别 | 问题 | 位置 | 状态 |
|------|------|------|------|
| P1 | `\\?\UNC\` 长前缀绕过 UNC 拦截（可触发 SMB 凭据外泄） | security.py validate_project/is_safe | ✅ 剥离后检查 `unc\` 前缀 + resolve 后复查网络盘符 |
| P1 | note/tag 端点自动注册任意目录（沙箱逃逸） | project_routes.py | ✅ 前置 `get_valid_project_root` 闸门 |
| P1 | MCP `--transport` 从未传入 run()，HTTP 模式不可用 | mcp_server.py | ✅ 转发 + `http`→`streamable-http` 别名 + SDK 字面量 |
| P1 | execute_tool 超时 killpg 自杀（POSIX） | actions.py | ✅ `start_new_session=(os.name!="nt")` |
| P1 | 坏配置被整体重写且无备份（数据丢失） | config.py save() | ✅ 先备份 `.corrupt-<ts>` 再重写 |
| P1 | 前端 categorize 后防抖写与 reload 竞态（staging 回跳） | main.js | ✅ `flushNow()` 先落盘再刷新 |
| P1 | 桌面端切换预览静默丢弃未保存编辑 | file_search.py | ✅ 未保存守卫（对比 `_last_loaded_preview`） |
| P2 | CancelledError 逃逸 + CANCELLED 态 future 令 as_completed 永久挂起 | search.py | ✅ 显式捕获 + done() 预收割 + 分片 wait |
| P2 | 背压阻塞不响应取消 | search.py | ✅ 0.1s 分片 + stop 检查 |
| P2 | 手动排除子路径模式在 Windows 永不生效 | file_io.py | ✅ 分隔符归一化 |
| P2 | get_metadata 降级 dict 缺键 → WS 搜索崩溃且被吞成 DONE | file_io.py + ws_routes.py | ✅ 补全契约 + ERROR 帧 |
| P2 | extract 的 zip_path UNC/任意路径 | fs_routes.py + actions.py | ✅ 双层拦截（resolve/exists 之前） |
| P2 | same_origin 信任 Host 头可被伪造绕过 | web_app.py | ✅ 仅回环主机或显式白名单视为同源 |
| P2 | 非 ASCII token 触发 500；WS close(4001) 在 accept 前永不达客户端 | web_app.py + ws_routes.py | ✅ encode 后比较；先 accept 再 close |
| P2 | 进程生命周期：shutdown 无清理 | web_app.py | ✅ lifespan 终止被跟踪进程 |
| P2 | DuplicateWorker 取消不发 DONE；GUI ERROR 分支不停 worker；after 未取消 | duplicate.py + gui | ✅ 全部修复 |
| P2 | 前端：空查询卡死 UI / 全选漏虚拟列表 / clipboard 非 Secure Context 必挂 / 亮色主题关闭按钮隐形 / 工具执行可重入 | main.js/ui.js/state.js/index.html/style.css | ✅ 全部修复 |
| P3 | 一批：schema Literal/边界、CLI 退出码、extract 残留目录、超时 env 解析、execute 跳过静默、pin 比较、copyPath 定时器、422 显示、api_token 读取时机、锁 fd 泄漏、`""` 项目键 | 多处 | ✅ 见 ROADMAP 6.6.0 清单 |

**未修复（有意延后至 Phase 2/3，见 IMPLEMENTATION_PLAN_V660.md §待办）**：Desktop 主线程同步 IO（导出/保存卡 UI）、桌面 poller 链增殖、WS 工具流无超时、stream_tool 孙进程泄漏、搜索 regex 模式语义陷阱（正则只搜路径不搜内容）、DM save 风暴（去抖）、save_content 编码回写风险、`regex→content` 模式语义、统一授权依赖、God Object 拆分、i18n。

## 7. 架构评分卡

| 维度 | 评分 | 说明 |
|------|------|------|
| 分层与依赖 | 8.5/10 | 单向、无环、内核纯净 |
| 安全设计 | 7.5/10 | 原语强，分布性弱（本轮已收敛主要旁路） |
| 一致性（四入口） | 6/10 | 行为矩阵碎片化 |
| 可测试性 | 8/10 | DI 钩子齐备但单例陷阱多 |
| 可维护性 | 6.5/10 | 三个 God Object + 按版本堆叠的测试 |
| 性能 | 7/10 | 有缓存意识；IO 放大模式若干 |
| 文档 | 9/10 | 四份联动文档 + 守卫测试，罕见地完整 |
| **综合** | **7.5/10** | 一个安全意识与工程纪律高于平均水平的项目，债务集中在结构而非质量 |
