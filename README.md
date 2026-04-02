# FileCortex v5.7.1 Production (工作区编排助手)

这是一个通用的 **工作区编排与文件处理工具 (Workspace Orchestrator)**。它可以帮助你高效地管理项目文件、执行自动化脚本、进行快速分类，并能一键导出结构化的上下文以供 AI 辅助编程使用。v5.7.1 版本引入了跨平台路径适配、UI 回调防崩保护及进程组级资源治理。

## 🌟 核心理念
*   **Orchestration over Collection**: 从简单的“收集”进化为对工作区的“编排”。

## 🌟 主要功能
- **多端支持**：提供本地桌面版 (Tkinter) 和 现代网页版 (FastAPI)，**通过 Path Casing 适配实现 100% 跨平台一致性**。
- **微内核架构 (v5.2)**：核心逻辑已完全迁移至 `file_cortex_core/` 包，支持作为库被第三方调用。
- **AI 上下文增强**：集成 **Token 实时估算 (FormatUtils)** 与 **Prompt 自动化模板**，并在 UI 中引入数千位分隔符展示。
- **高性能加载**：网页版支持目录懒加载、**自适应并发多线程搜索** 及 **二进制检测 Fast-path**。
- **ActionBridge 异步流 (Real-time Streaming)**：支持外部编排工具的 `stdout` 实时推送。
- **智能分类建议 (Smart Suggestions)**：基于文件模式自动推荐编排工具。
- **跨平台系统剪切板**：支持 Windows/macOS/Linux 的原生文件复制。
- **原子化持久化与自愈**：内核级项目配置 Schema 自动对齐、**线程安全单例模型** 及 原子化写入。
- **配置安全白名单 (v5.3)**: Settings API 强制字段白名单，防止恶意配置注入（RCE 链防御）。
- **跨项目移动防护 (v5.3)**: Move API 拒绝跨越项目边界的文件移动，确保数据隔离。
- **资源管理强化 (v5.7.1)**: 强制回收搜索生成器 Future 任务，并支持 Unix 进程组彻底清理。
- **标签化多重过滤 (v5.5)**: 支持正向包含、反向排除及局部正则标签，实现复杂的工程级文件筛选。
- **极速查重工具 (v5.5)**: 引入 `DuplicateWorker`（后台线程），采用“大小预筛 + SHA256 哈希”策略。
- **现代化 UI 加固 (v5.7.1)**: 全面升级为 `ttk.Scrollbar`，引入 UI 统计防抖 (300ms) 及 消息队列智能关闭。
- **工业级并发加固 (v5.7.1)**: DataManager 全局原子锁、共享线程池优化，彻底杜绝高并发下的配置损坏。
- **内存安全与 OOM 防护 (v5.7)**: 采用流式编码探测与智能文本读取 (`read_text_smart`)，即使处理 100MB+ 日志文件也不会导致系统 OOM。
- **可视化 Web 增强 (v5.7)**: 玻璃拟态增强设计、顺序化多任务工具执行引擎及 100% 流程状态反馈。
- **快速路径搜集 (v5.3+)**: 极大简化路径编排工作流，支持自定义分隔符与相对/绝对路径转换。
- **工作区常驻与历史 (v5.3+)**: 自动记录最近使用的 15 个项目，支持置顶 (Pin) 常用工作区并还原专属配置（过滤、模式等）。
- **健壮的错误处理**: UI 渲染回调加入全局异常守卫，确保核心流程不因个别数据异常而崩溃。

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

**124+ 自动测试 (124+ Automated Tests)**: `pytest` 全覆盖。测试环境实现了 **DataManager 强制隔离重置**，确保跨平台逻辑的绝对可靠性：
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
