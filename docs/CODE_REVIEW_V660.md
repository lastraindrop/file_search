# FileCortex v6.6.0 完整 Code Review 报告

> 方法：四路并行深度审查（core / web+入口 / 前端+GUI / 测试）+ 全部 P1 与代表性 P2 的人工源码复核
> 级别定义：P1=安全旁路或数据丢失；P2=用户可感知的功能缺陷；P3=打磨项
> 标记：✅=v6.6.0 已修复并附回归测试；⏳=已排期（见 IMPLEMENTATION_PLAN_V660.md）；ℹ️=设计取舍/记录在案
> 行号以 v6.5.3 基线（0537cac）为准，修复后行号有少量漂移。

---

## 1. file_cortex_core/security.py

| 级别 | 位置 | 问题 | 状态 |
|------|------|------|------|
| P1 | security.py:169-182 | `\\?\UNC\evil\share` 被 `_strip_win_long_prefix` 剥成 `UNC\evil\share` 后不再以 `\\` 开头，**绕过 UNC 拦截**；随后 180 行 `resolve()`/182 行 `exists()` 真实发起 SMB 认证——恰是该检查声称要防的事 | ✅ 剥离后检查 `unc\` 前缀（不区分大小写）+ resolve 后复查网络盘符 |
| P1 | security.py:37-106 | `is_safe` 同样存在长前缀 UNC 绕过（`\\?\UNC\...` 目标被当相对路径拼进 root 后通过） | ✅ 同上修复 |
| P3 | security.py:81-101 | resolve-再比较是 check-then-use，symlink 在检查后创建仍有 TOCTOU（固有风险） | ℹ️ 文档标注 |
| P3 | security.py:130 | `norm_path` 在 POSIX 上对 Windows 风格输入产出 `/home/u/C:\x` 垃圾键 | ⏳ Phase 2 |

## 2. file_cortex_core/config.py

| 级别 | 位置 | 问题 | 状态 |
|------|------|------|------|
| P1 | config.py:456-497 | 磁盘配置损坏时 save() 用 `_base_config_data`（可能是全默认值——load 失败被 445 行吞掉）**整体重写** config.json，projects/notes/tags 全丢且无备份 | ✅ 重写前先 `shutil.copy2` 备份为 `config.json.corrupt-<ts>` |
| P2 | config.py:88-104 | 陈旧锁打破 TOCTOU：B 读到死锁 owner 后、unlink 前，A 可能已重建自己的新锁，B 误删 A 的锁 → 双进程同持锁 | ✅ unlink 前重读 owner 确认仍是同一死锁 |
| P2 | config.py:62-69 | `_is_process_alive`：OpenProcess 对他人/提权进程返回 ACCESS_DENIED 被当"已死"→ 误打破活锁（叠加上一条后果） | ✂️ 区分 `GetLastError()==5` 视为存活；补 argtypes/restype |
| P3 | config.py:82-84 | `os.write`/`os.close` 失败 fd 泄漏 | ✅ try/finally |
| P3 | config.py:100 | except 分支内再 `stat()` 可能 FileNotFoundError 二次抛出 | ✅ 捕获后 continue |
| P3 | config.py:110-112 | finally 中 `read_text` PermissionError（杀软占用）掩盖原异常 | ✅ suppress 拓宽到 OSError |
| P3 | config.py:564-577 | `get_project_data_obj` 对空路径创建 `projects[""]` 脏键（`add_note("")` 即触发） | ✅ raise ValueError（含 None） |
| P3 | config.py:137-138 | 冲突列表合并 `[*disk, *local]` 与 add_to_recent 的"最新在头"语义相反 | ⏳ Phase 2 |
| P2 | config.py:448-504+各 mutator | 每次小改动全量"锁+读盘+合并+写"（save 风暴）；save 持 RLock 等文件锁最长 10s，阻塞所有线程 | ⏳ Phase 2（脏标记+去抖） |
| P3 | config.py:226-259 | logger 混入配置模块；import 即建目录副作用；未设 propagate=False | ⏳ Phase 2（logging_setup.py） |
| P3 | config.py:169 | `sessions: list[dict]` 无形状校验 | ⏳ Phase 2 |
| P3 | config.py:593-603 | `batch_stage` 不做 is_safe（对比 update_project_settings 做了），同一数据两条写入路径强度不一 | ⏳ Phase 2 统一授权 |

## 3. file_cortex_core/search.py

| 级别 | 位置 | 问题 | 状态 |
|------|------|------|------|
| P2 | search.py:347,369,448 | 池 reinit 取消在途 future → `f.result()` 抛 `CancelledError`（**BaseException**），`except Exception` 捕不住 → 生成器/线程死亡，UI 永远等 DONE | ✅ 三处显式捕获 |
| P2 | search.py:393 最终收割 | `as_completed`/`wait` **永不回报 CANCELLED 态**（只认 CANCELLED_AND_NOTIFIED/FINISHED）——收割前已被取消的 future 令循环永久挂起（比上一条更隐蔽，实测复现） | ✅ 重写为"done() 预收割 + 0.2s 分片 wait + stop 检查" |
| P2 | search.py:341-344 | 背压 `next(as_completed(...))` 无限阻塞且期间不查 stop_event，取消延迟秒级 | ✅ `wait(timeout=0.1, FIRST_COMPLETED)` 分片循环 |
| P3 | search.py:98-101 | `SearchQuery.max_results/max_size_mb` 无约束；`max_size_mb` 为负 → `read_text_smart(max_bytes=负)` → `f.read(-1)` **读整个文件** | ✅ Field 边界 + read_text_smart 非正数守卫 |
| P3 | search.py:193-229 | ContentMatcher 的 regex 分支不可达：regex 模式只走路径匹配——"正则搜内容"语义陷阱 + 死代码 | ⏳ Phase 3（语义决策：regex+content 合并或文档化） |
| P3 | search.py:314-317 | 路径模式对全树每文件先 get_metadata（resolve+stat）后判命中 | ⏳ Phase 2（性能） |
| P3 | search.py:57-60 | 每次 reinit 追加注册一个新 atexit 回调 | ℹ️ 记录 |
| P3 | search.py:130-135 | `/regex/` 标签与 POSIX 绝对路径标签歧义 | ℹ️ 记录 |

## 4. file_cortex_core/file_io.py

| 级别 | 位置 | 问题 | 状态 |
|------|------|------|------|
| P2 | file_io.py:213-216 | 手动排除模式对 `str(rel_path)` fnmatch，Windows 产生反斜杠 → `docs/*`、`build/**` 等 gitignore 风格子路径模式**永不生效** | ✅ 匹配前统一 `/`（与 git_spec 分支 219 行对齐） |
| P2 | file_io.py:467-474 | `get_metadata` 异常 fallback 缺 `path/type/size_fmt/mtime_fmt` 键 → ws_routes:117 `res_dict["path"]` KeyError | ✅ fallback 补全全部成功分支键 |
| P3 | file_io.py:115-116 | `is_binary` 对不存在文件返回 False（"非二进制"）语义含糊 | ℹ️ 记录 |
| P3 | file_io.py:150-152 | `clear_cache` 只清 gitignore 缓存，编码缓存不受管（命名歧义） | ⏳ Phase 2 |
| P3 | file_io.py:437 | `get_language_tag` 的 `"dockerfile"`（无点）键永不匹配 | ⏳ 顺手修 |
| P3 | file_io.py:53-58 | `relative_to` 失败兜底 normcase 破坏大小写敏感 gitignore 规则 | ℹ️ 记录 |
| P3 | file_io.py:74-80 | walk 文件内层循环无 stop 检查 | ⏳ Phase 2 |

## 5. file_cortex_core/actions.py

| 级别 | 位置 | 问题 | 状态 |
|------|------|------|------|
| P1 | actions.py:1058-1069 | `execute_tool` 的 Popen **无 `start_new_session`**（对比 create_process:1134 有）；超时 `terminate_process` 执行 `killpg(getpgid(pid))` = **SIGTERM 服务器自身进程组**（POSIX 部署下任何工具超时=服务自毁） | ✅ `start_new_session=(os.name != "nt")` |
| P2 | actions.py:807-824 | extract 的 zip_path 零 UNC 拦截：`is_zipfile/open` 触发 SMB(NTLM) 认证尝试；dst 校验完备唯独源失控 | ✅ core 层在 resolve/exists **之前**拦截（Web 路由同步加闸） |
| P3 | actions.py:824 | extract 在 Pass1 校验前 mkdir，失败残留空目录 | ✅ 校验通过后才建目录 |
| P2 | actions.py:1158-1177 | `stream_tool`：shell 孙进程持有管道 → 迭代永久阻塞 + terminate 只杀 cmd.exe，孙进程与句柄泄漏 | ⏳ Phase 2（Windows Job Object） |
| P3 | actions.py:1013-1025 | 空模板→`shutil.which("")`；Windows 非 shell 先 format 再 shlex 拆分，路径含空格且模板无引号时 argv 错乱；`%` 双写对交互 cmd 语义错误 | ⏳ Phase 2 |
| P3 | actions.py:418-426 | `save_content` 用探测编码回写（只看 64KB 头），误判时直接写坏文件且无备份 | ⏳ Phase 2（写前备份或强制 UTF-8 选项） |
| P3 | actions.py:363-370 | 删除指向目录的 symlink 走 rmtree 报错信息不明 | ⏳ 顺手修 |
| P3 | actions.py:466-524 | archive 无成员数/总量上限（解压侧有） | ⏳ Phase 2 对称限制 |
| P3 | actions.py:673-683 | copy 回滚失败残留仅记日志不告知调用方 | ℹ️ 记录 |

## 6. file_cortex_core/duplicate.py + gui/

| 级别 | 位置 | 问题 | 状态 |
|------|------|------|------|
| P2 | duplicate.py:89-112 | 三处 stop 命中直接 return，不发 DONE 哨兵——公开 API 复用方按约定轮询会永久等待 | ✅ `_cancelled()` 辅助统一发哨兵 |
| P2 | gui/duplicate_finder.py:138-141 | ERROR 分支 showerror+destroy 但**不 set stop_event**，worker 继续对全工作区 SHA256 | ✅ |
| P2 | gui/duplicate_finder.py:177+268 | `after(200)` 链未取消，destroy 后 Tcl 计时器在死 widget 上抛 TclError | ✅ after_id + after_cancel + winfo_exists 守卫 |
| P2 | gui/batch_rename.py:190-201 | simple 模式只转义 pattern 不转义 replacement：`\new` 抛 `re.error: bad escape` 或静默注入 `\n`/`\t` | ✅ 提取 `build_literal_substitution()` 纯函数（双侧转义） |
| P2 | gui/path_collection.py:178-181 | clipboard_append 后立即 destroy，Tk 剪贴板随窗口销毁丢失 | ✅ destroy 前 `update()` |
| P3 | gui/batch_rename.py:83-88 | 每击键全量 dry_run 无防抖，大选中集卡顿 | ⏳ Phase 2 |
| P3 | gui/duplicate_finder.py:254-266 | 删除后 groups 不更新、smart_select 重选已删文件、失败连环弹窗 | ⏳ Phase 2 |

## 7. web_app.py + routers/

| 级别 | 位置 | 问题 | 状态 |
|------|------|------|------|
| **P1** | project_routes.py:99-117 | **note/tag 自动注册旁路**：仅 `is_safe(file, project_path)` 纯包含检查，`get_project_data_obj` 就地注册任意目录（如 `C:/Windows`）并持久化 → `resolve_project_root` 此后认可该根，/api/content、/ws/search、/api/fs/* 全部对系统目录开放——**完全绕过 validate_project 黑名单**（四入口中唯一旁路） | ✅ 两端点前置 `get_valid_project_root` 闸门 |
| P2 | web_app.py:84 | `same_origin = origin == str(request.base_url).rstrip("/")`：base_url 派生自**客户端可控 Host 头**，伪造 `Origin+Host` 同值即通过同源判定（token 缺失时的 CSRF 防线） | ✅ 仅回环主机或显式白名单视为同源 |
| P2 | web_app.py:96-98 | `compare_digest(str,str)` 非 ASCII 抛 TypeError → 500 | ✅ encode 后比较（WS 同步修复） |
| P2 | web_app.py:132-150 | 无 lifespan/shutdown：退出/reload 时被跟踪子进程孤儿化（POSIX 下叠加 start_new_session 更彻底） | ✅ lifespan 遍历终止 |
| P2 | fs_routes.py:402-428 | extract 的 zip_path 零边界校验直传 core（UNC+SMB 向量） | ✅ 路由层拦截 + core 层兜底 |
| P2 | ws_routes.py:94-129 | run_search 无 except：线程异常被 finally 的 DONE 吞掉，**搜索半路炸了客户端以为正常结束**（触发链即 file_io fallback 缺键） | ✅ except → ERROR 帧（与 run_stream 对齐） |
| P2 | ws_routes.py:58-59,168-169 | accept 前 `close(4001)`：Starlette 以 HTTP 403 拒握手，自定义码永不到达浏览器 | ✅ 先 accept 再 close |
| P2 | ws_routes.py:158-280 | 工具执行 WS 无超时（HTTP 版 300s），连接保持即进程无限跑并占用全局 50 容量 | ⏳ Phase 2 |
| P3 | action_routes.py:233 | `int(env)` 每 path 抛一次 ValueError 落入误导性错误 | ✅ 解析一次 + 回退 300 |
| P3 | action_routes.py:221-223 | 不安全路径静默 continue（WS 发 ERROR/CLI 打印/桌面过滤，四入口四种行为，HTTP 最差） | ✅ 报告 skipped 项 |
| P3 | web_app.py:180 | 本地 peer 注入 token：SSH 端口转发/反代下远程方 peer 也是 127.0.0.1，token 泄给远程页面 | ⏳ Phase 2（一次性 ticket） |
| P3 | fs_routes.py:118 等 7 处 | `except Exception → 400(str(e))`：内部错误压成 400 且回显绝对路径/异常文本 | ⏳ Phase 2（错误分类） |
| P3 | schemas.py:47,176,297 | export_format 自由 str（"XML" 静默落 markdown）、tag 无长度上限、count 无下界 | ✅ Literal + max_length + ge |
| P3 | common.py:97-98 | 导出 `_processes`/`_lock` 私有本体，绕过容量/锁语义 | ⏳ Phase 2 封装收敛 |
| P3 | services.py:93-100 | symlink 目录项回退词法前缀判断仍列出（显示打不开的节点） | ℹ️ 记录 |

## 8. mcp_server.py / fctx.py / build_exe.py

| 级别 | 位置 | 问题 | 状态 |
|------|------|------|------|
| **P1** | mcp_server.py:354-364 | `--transport` 解析后**从未使用**：`run(host=..., port=...)` 不传 transport，选 http 实际仍跑 stdio（或 SDK 因多余 kwargs 报错）；且 `http` 非官方字面量（应为 sse/streamable-http） | ✅ 转发 + 别名映射 + choices 对齐 SDK |
| P3 | mcp_server.py:158 | 上限实为 51（off-by-one）且不提示截断 | ✅ 50 条 + 截断说明 |
| P3 | mcp_server.py:199-201 | fmt 自由 str | ✅ 归一化大小写 |
| P2 | mcp_server.py:74-103 | 猴补 `mcp.tool` 注册失败时 `except: return func` 静默降级，自建注册表与真实服务端可分叉 | ⏳ Phase 2 |
| P3 | mcp_server.py:314-319 | stats 越界静默跳过 vs context 报警告（同文件双标） | ⏳ 顺手修 |
| P3 | mcp_server.py:138 等 | 错误以字符串返回而非 isError 协议语义 | ⏳ Phase 3（协议升级） |
| P3 | fctx.py:437-438 | 无子命令 print_help 后退出码 0，CI 无法凭码发现 | ✅ exit 2（3 个旧测试同步更新） |
| P3 | fctx.py:186-191 | export `--output` 绝对路径任意写（与 Web save 严格沙箱不对称） | ℹ️ 本地 CLI=用户权限，记录在案 |
| P3 | fctx.py | 无 unstage/delete/move 等（stage 进得去出不来）；excludes 忽略项目配置 | ⏳ Phase 2 |
| P3 | build_exe.py | 仅打包桌面版，其余三入口不在产物 | ⏳ Phase 2 文档/补充 |

## 9. 前端（static/js + templates + css）

| 级别 | 位置 | 问题 | 状态 |
|------|------|------|------|
| **P1** | main.js:904-922 | categorize 后 `syncStagingToBackend()`（500ms 防抖）与 `refreshProject()` 竞态：reload 先读到旧 staging_list 覆盖 UI，防抖写完不再重渲染——**前后端持续不一致** | ✅ `flushNow()` 先落盘再刷新 |
| P2 | main.js:793-804 | 空查询先 `++searchGeneration` 再 return：后台搜索的 socket 存活但 onmessage/onclose 全部失效 → 停止按钮永不隐藏、overlay 永久 "Searching..." | ✅ 空查询校验移到自增之前 |
| P2 | main.js:1255-1292 | 全选基于 `querySelectorAll`——虚拟列表只渲染可见 ~30 条，全选只选子集且先 `clear()` 清掉用户已选的屏外项 | ✅ 树 DOM + state.searchResults 并集 |
| P2 | main.js:1218/1597 等 4 处 | `navigator.clipboard` 在非 localhost 的 http（LAN 部署形态）下 undefined——核心卖点 Copy Context **远程必挂** | ✅ state.js `copyToClipboard` 带 execCommand 回退 |
| P2 | main.js:924-1034 | executeToolOnStaged 可重入：双击并行两条 runNext 链交错输出、socket/pid 相互覆盖 | ✅ `toolRunInFlight` 守卫（state.js 同步声明） |
| P2 | style.css:1029-1031 | 亮色主题 `.btn-close-white{filter:none}` → 白色关闭钮在浅底上**隐形** | ✅ `invert(1)` |
| P3 | index.html:106-119 | 全选控件在 `#bulkActions`（零选中即隐藏）内——鸡生蛋不可达 | ✅ 常显 + 按钮禁用态 |
| P3 | api.js:14-21 | 422 的 detail 是数组，`new Error(数组)` 显示 `[object Object]` | ✅ 展开为 msg 串 |
| P3 | main.js:881-892 | stopSearch 计数只数虚拟列表已渲染项 | ✅ 用 state.searchResults |
| P3 | ui.js:138 | isPinned 用原始串比较，手打路径变体时状态错误 | ✅ 归一化比较 |
| P3 | main.js:506-518 | copyPath 双击时 1 秒还原定时器捕获到 "Copied"，按钮永久停留 | ✅ data-orig-label + clearTimeout |
| P3 | main.js:485-498 | marked/mermaid 无加载守卫（DOMPurify 有） | ⏳ 顺手修 |
| P3 | main.js:13-16 | `...api,...ui` 展开同名遮蔽风险（saveGlobalSettings 现状碰巧正确） | ⏳ Phase 2 拆分 |
| P3 | state.js:69-89 | `activeToolSocket` 未声明（动态添加） | ✅ 连同 toolRunInFlight 一并声明 |
| 安全面 | 全部 innerHTML 注入点 | 逐一核验：toast/收藏/搜索/树/modal/MD 预览全部 escapeHtml 或 DOMPurify 覆盖，**未发现可利用 XSS** | ℹ️ 保持纪律（meta 注入 token 使 XSS 收益升格） |

## 10. 桌面版 file_search.py

| 级别 | 位置 | 问题 | 状态 |
|------|------|------|------|
| **P1** | 1271-1323 | `on_tree_select_preview` 直接 `delete("1.0", END)` 覆盖编辑中内容，无确认（Web 有 Discard 弹窗）——点一下树节点丢全部未保存修改 | ✅ 脏检测 + askyesno 守卫（`_last_loaded_preview` 快照） |
| P2 | 1567-1597 | `copy_all_staging_content` 主线程同步读盘生成上下文，大 staging 冻结 UI 数秒~数十秒 | ⏳ Phase 2（后台线程化） |
| P2 | 1408-1454 | staging 过滤 trace 每键对全表 `exists()+stat()`，路径消失还触发全量配置落盘 | ⏳ Phase 2 |
| P3 | 1149-1231 | poller 链可增殖（自愈但有叠加期） | ⏳ Phase 2 |
| P3 | 1737-1767 | ctx_copy_file_to_os 主线程 subprocess.run 冻结 | ⏳ Phase 2 |
| P3 | 1057-1077 | Enter 即把搜索词固化为 persistent tag，无 UI 提示，与 Web 心智模型不同 | ⏳ Phase 3（统一搜索语义） |
| P3 | 96/104 等 | 未定义的 ttk Style（Danger/Accent）静默回退 | ⏳ 顺手修 |

## 11. 测试体系

| 级别 | 位置 | 问题 | 状态 |
|------|------|------|------|
| 盲区 | tests/ | `/api/actions/execute` happy path、`/api/fs/move|delete` happy path 零覆盖 | ✅ execute 已补（超时解析+跳过报告）；move/delete ⏳ Phase 2 |
| 盲区 | tests/ | GUI/Tk 零行为测试；前端无执行级测试 | ⏳ Phase 2（纯逻辑抽取 + Playwright） |
| 质量 | test_bugfix_v633/653 等 | ~8 个"测试 Python 标准库"自证用例；40 组重名用例 | ⏳ Phase 2（重组为按模块单测） |
| 结构 | conftest.py:61 | 每 0.2s 锁等待 ×N 全量 ≈170s 结构性慢 | ⏳ Phase 2（marker 化） |
| 记录 | tests/README:56 | `pytest -m "not slow"` 指令无效（无注册 marker）；pytest-asyncio 为隐式依赖 | ⏳ 顺手修 |

---

## 12. 统计与结论

- 审查发现：**P1 ×9**（全部修复）、**P2 ×28**（修复 21，排期 7）、**P3 ×60+**（修复 ~20，其余排期/记录）。
- 本轮新增回归测试 46 项（tests/test_v660_review_fixes.py），全量 **846 passed / Ruff 0 errors**；更新既有测试 4 处以匹配新的正确行为（WS 4001 交付方式、CLI 退出码 ×3）。
- 修复顺序遵循"安全旁路 → 数据完整性 → 挂起/竞态 → 可用性/打磨"，每一项修复均有对应回归测试锚定（映射表见 IMPLEMENTATION_PLAN_V660.md §3）。
- 遗留风险最高的三项（已排期）：① WS 工具流无超时；② stream_tool 孙进程泄漏；③ DataManager save 风暴。建议 Phase 2 优先处理。
