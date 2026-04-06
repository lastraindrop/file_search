# FileCortex v5.8.2 Production (工作区编排助手)

这是一个通用的 **工作区编排与文件处理工具 (Workspace Orchestrator)**。它可以帮助你高效地管理项目文件、执行自动化脚本、进行快速分类，并能一键导出结构化的上下文以供 AI 辅助编程使用。v5.8.2 版本引入了 CJK 加权 Token 预估、后端全局异常监控及前端网络层标准化改进。

## 🌟 核心理念
*   **Orchestration over Collection**: 从简单的“收集”进化为对工作区的“编排”。

## 🌟 主要功能
- **多端支持**：提供本地桌面版 (Tkinter) 和 现代网页版 (FastAPI)，**通过 Path Casing 适配实现 100% 跨平台一致性**。
- **微内核架构 (v5.2)**：核心逻辑已完全迁移至 `file_cortex_core/` 包，支持作为库被第三方调用。
- **AI 上下文增强 (v5.8.2)**：集成 **中日韩加权 Token 估算 (FormatUtils)**、**Token 预算预警** 与 **Prompt 自动化模板**。
- **路径搜集预设 (v5.8.2)**：支持自定义文件前缀 (Prefix) 与 目录后缀 (Suffix)，内置 GPT/RAG 多套搜集预设。
- **高性能加载**：网页版支持目录懒加载、**自适应并发多线程搜索** 及 **二进制检测 Fast-path**。
- **ActionBridge 指令加固 (v5.8.2)**：自动识别 Windows 内置指令 (Echo/Dir)，支持环境变量转义 (`%%`)，彻底杜绝注入扩展风险。
- **智能化清单过滤器 (v5.8.0)**：支持清单内容的实时搜索过滤与批量按类移除。
- **预览区内容检索 (v5.8.0)**：桌面端预览支持 `Ctrl+F` 高亮关键词查找。
- **ActionBridge 异步流 (Real-time Streaming)**：支持外部编排工具的 `stdout` 实时推送。
- **原子化持久化与自愈**：内核级项目配置 Schema 自动对齐、**线程安全单例模型 (RLock)** 及 原子化写入。
- [x] **[DONE] 增量生产加固 (v5.8.2)**: 
    - **安全闭锁**: 实现了 UNC/网络路径拦截 (S1) 与 AppleScript 注入拦截 (S6)。
    - **并发鲁棒性**: DataManager 实现了方法级 RLock 全流程保护 (B5-B7)，修复了 Web 并发下的配置竞态。
    - **前端 DX 进化**: 引入代码编辑器 Tab 缩进、Ctrl+S 快速保存、及文件切换“脏数据”检查。
    - **搜索逻辑对齐**: 修复了正则搜索无法匹配全路径的 Bug (B10)，实现动态参数 100% 对齐。
    - **资源治理**: 修复了背景统计线程 (B1) 与 Staging 列表同步 (B3) 缺陷。
    - **输入溢出防御**: 增加了 FileSaveRequest 的 10MB 长度限制 (S3) 与生成 Context 的 OOM 熔断保护。
    - **内核稳定性**: 补齐了 183 项全自动化回归测试 (Pytest)。
- **极速查重工具 (v5.5)**：引入 `DuplicateWorker`（后台线程），采用“大小预筛 + SHA256 哈希”策略。
- **非侵入式 UI 反馈 (v5.8.0)**：桌面端引入 Status Stream 机制，减少阻塞式 Messagebox 弹出。
- **工业级并发加固 (v5.8.0)**：DataManager 方法级原子锁、共享线程池优化，彻底杜绝高并发下的配置损坏。
- **原子化配置持久化 (v5.7.1)**：DataManager 采用 `NamedTemporaryFile` + `os.replace` 策略。
- **强制进程治理 (v5.7.1)**：实现外部工具 300s 强制超时暗杀 logic，配合 Windows/Unix 树级清理。
- **内存安全与 OOM 防护 (v5.7)**：采用流式编码探测与智能文本读取 (`read_text_smart`)。
- **可视化 Web 增强 (v5.7)**：玻璃拟态增强设计、顺序化多任务工具执行引擎。
- **工作区常驻与历史 (v5.3+)**：自动记录最近使用的 15 个项目，支持置顶 (Pin) 常用工作区。
- **健壮的错误处理**: UI 渲染回调加入全局异常守卫，UI 轮询加入容错机制。


## 📚 详细文档
- [开发者说明 (Architecture & Security)](DEVELOPER_GUIDE.md)
- [项目路线图 (Roadmap)](ROADMAP.md)
- [Pytest 测试说明](tests/README.md)

## 🚀 快速开始

### 桌面版
- **已打包用户**：下载并解压，双击 `dist/FileCortex.exe`。
- **开发者**：
  ```bash
  pip install -r requirements.txt
  python file_search.py
  ```

### 网页版
1. 运行启动脚本：
   ```bash
   python web_app.py
   ```
2. 在浏览器中访问：`http://127.0.0.1:8000`

- **183+ 自动测试 (183+ Automated Tests)**: `pytest` 全覆盖。测试环境实现了 **DataManager 强制隔离重置** 与 **Windows 进程树强制杀伤**，确保跨平台逻辑的绝对可靠性：
```bash
python -m pytest
```

## 🛠 开发与部署

### 依赖安装
```bash
pip install -r requirements.txt
```

### 重新打包 EXE
```bash
python build_exe.py
```

## 📂 项目结构
- `file_cortex_core/`: 微内核逻辑包（配置、安全、工具、行为、搜索）。
- `fctx.py`: CLI orchestration tool for headless workspace management.
- `web_app.py`: FastAPI backend and modern web interface.
- `file_search.py`: Tkinter-based desktop GUI for local orchestration.
- `tests/`: 自动化测试套件（新架构下的拆分式测试）。
- `static/` & `templates/`: Web 静态资源与模板。
- `build_exe.py`: 自动化打包脚本。
- **参数动态对齐协议 (Parameter Alignment Protocol - v5.8)**: 
    - **API 上下文保障**: 任何涉及文件列表统计（如 `StatsRequest`）或内容生成（如 `GenerateRequest`）的模型必须显式包含 `project_path`。
    - **UI 过滤器同步**: 桌面端清单过滤器 (`staging_filter`) 与后端统计逻辑通过动态对齐协议实现 100% 同步，确保“所见即所得”的统计体验。
    - **OOM 拦截规约**: 所有的文本读取操作必须调用 `FileUtils.read_text_smart`。该方法限制了编码采样的最大字节数，并在读取前进行二进制检测，防止因读取 GB 级日志而发生 OOM 崩溃。**v5.8.0 进一步将 Context 生成限制在 1MB/文件，防止批量导出时发生内存溢出。**
    - **UI 回调防御 (Audit Fix - v5.7.1)**: 为了防止 Tkinter 回调中的 `AttributeError` 导致界面静默失效，所有 UI 渲染回调（如 `_update_stats_ui`）必须包含 `try...except` 保护。

## 📝 许可证
MIT License
