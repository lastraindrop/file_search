# FileCortex v5.3 (工作区编排助手)

这是一个通用的 **工作区编排与文件处理工具 (Workspace Orchestrator)**。它可以帮助你高效地管理项目文件、执行自动化脚本、进行快速分类，并能一键导出结构化的上下文以供 AI 辅助编程使用。v5.3 版本完成了基于完整 Code Review 的全面安全加固与可靠性闭环。

## 🌟 核心理念
*   **Orchestration over Collection**: 从简单的“收集”进化为对工作区的“编排”。

## 🌟 主要功能
- **多端支持**：提供本地桌面版 (Tkinter) 和 现代网页版 (FastAPI)，**真正支持 Windows/macOS/Linux 跨平台运行**。
- **微内核架构 (v5.2)**：核心逻辑已完全迁移至 `file_cortex_core/` 包，实现高内聚低耦合，支持作为库被第三方调用。
- **AI 上下文增强**：集成 **Token 实时估算 (FormatUtils)** 与 **Prompt 自动化模板 (Prompt Templates)**，极大优化 LLM 辅助编程的工作流。
- **高性能加载**：网页版支持目录懒加载、**自适应并发多线程搜索** 及 **二进制检测 Fast-path**。
- **ActionBridge 异步流 (Real-time Streaming)**：支持外部编排工具的 `stdout` 实时推送。
- **智能分类建议 (Smart Suggestions)**：基于文件模式自动推荐编排工具。
- **跨平台系统剪切板**：支持 Windows/macOS/Linux 的原生文件复制。
- **原子化持久化与自愈**：内核级项目配置 Schema 自动对齐、**线程安全单例模型** 及 原子化写入。
- **配置安全白名单 (v5.3)**: Settings API 强制字段白名单，防止恶意配置注入（RCE 链防御）。
- **跨项目移动防护 (v5.3)**: Move API 拒绝跨越项目边界的文件移动，确保数据隔离。
- **资源管理强化 (v5.3)**: 修复 `os.scandir()` 句柄泄漏，优化 WebSocket 断连清理逻辑。
- **现代化 Web UI (v5.3 PRO)**: 引入玻璃拟态增强设计、文件树多选 Checkbox、以及全流程加载状态反馈。
- **快速路径搜集 (v5.3+)**: 极大简化路径编排工作流，支持自定义分隔符与相对/绝对路径转换。
- **工作区常驻与历史 (v5.3+)**: 自动记录最近使用的 15 个项目，支持置顶 (Pin) 常用工作区并还原专属配置（过滤、模式等）。
- **健壮的错误处理**: 前端 `_fetch` 机制确保所有 API 拦截（如 403）均有即时 UI 弹窗提示。

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

项目包含 **72** 项覆盖核心逻辑、API、并发压力及 AI 工作流 E2E 的 `pytest` 测试。测试环境实现了 **DataManager 强制隔离重置**，确保跨平台逻辑的绝对可靠性：
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

## 📝 许可证
MIT License
