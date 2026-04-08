# FileCortex v6.0 Stable Release (工作区编排助手)

这是一个通用的 **工作区编排与文件处理工具 (Workspace Orchestrator)**。它可以帮助你高效地管理项目文件、通过 **Categorizer (分类器)** 整理目录、执行自动化脚本，并能一键导出结构化的上下文以供 AI 辅助编程使用。v6.0 版本引入了三栏式分类器 UI、226 项回归测试加固及 API 深度契约对齐。

## 🌟 核心理念
*   **Orchestration over Collection**: 从简单的“收集”进化为对工作区的“编排”。

## 🌟 主要功能
- **文件分类器 (Categorizer - v6.0)**：引入三栏式（列表、预览、分类按钮）UI，支持自定义物理路径映射。
- **226 项工业级加固 (v6.0 Hardened)**：补齐了针对架构适配、参数组合及 API 契约的 226 项全自动化回归测试。
- **API 深度契约协议 (v6.0 Contract)**：统一所有端点的响应 Schema，支持 `is_truncated`, `encoding` 等 UI 级自洽反馈。
- **多端支持**：提供本地桌面版 (Tkinter) 和 现代网页版 (FastAPI)，**通过 Path Casing 适配实现 100% 跨平台一致性**。
- **微内核架构 (v5.2)**：核心逻辑已完全迁移至 `file_cortex_core/` 包，支持作为库被第三方调用。
- **AI 上下文增强**：集成 **中日韩加权 Token 估算 (FormatUtils)**、**Token 预算预警** 与 **Prompt 自动化模板**。
- **路径搜集预设**：支持自定义文件前缀 (Prefix) 与 目录后缀 (Suffix)，内置 GPT/RAG 多套搜集预设。
- **高性能加载**：网页版支持目录懒加载、**自适应并发多线程搜索** 及 **二进制检测 Fast-path**。
- **ActionBridge 指令加固**：自动识别 Windows 内置指令 (Echo/Dir)，支持环境变量转义 (`%%`)，彻底杜绝注入扩展风险。
- **智能化清单过滤器**：支持清单内容的实时搜索过滤与批量按类移除。
- **预览区内容检索**：桌面端预览支持 `Ctrl+F` 高亮关键词查找。
- **ActionBridge 异步流 (Real-time Streaming)**：支持外部编排工具的 `stdout` 实时推送。
- **原子化持久化与自愈**：内核级项目配置 Schema 自动对齐、**线程安全单例模型 (RLock)** 及 原子化写入。
- **安全路径监控**：UNC/网络路径拦截、AppleScript 注入拦截及基于白名单的 Settings 修改保护。
- **强制资源治理**：外部工具 300s 强制超时暗杀、Windows/Unix 树级进程清理以及 `os.scandir` 句柄自动回收机制。
- **极速查重工具**：引入 `DuplicateWorker`（后台线程），采用“大小预筛 + SHA256 哈希”策略。
- **非侵入式 UI 反馈**：桌面端引入 Status Stream 机制，减少阻塞式 Messagebox 弹出。
- **内存安全与 OOM 防护**：采用流式编码探测与智能文本读取 (`read_text_smart`)。
- **工作区常驻与历史**：自动记录最近使用的 15 个项目，支持置顶 (Pin) 常用工作区。
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
