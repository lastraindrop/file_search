# FileCortex v5.8 Production (工作区编排助手)

这是一个通用的 **工作区编排与文件处理工具 (Workspace Orchestrator)**。它可以帮助你高效地管理项目文件、执行自动化脚本、进行快速分类，并能一键导出结构化的上下文以供 AI 辅助编程使用。v5.8 版本引入了环境变量注入防御、非侵入式反馈流及工业级并发加固。

## 🌟 核心理念
*   **Orchestration over Collection**: 从简单的“收集”进化为对工作区的“编排”。

## 🌟 主要功能
- **多端支持**：提供本地桌面版 (Tkinter) 和 现代网页版 (FastAPI)，**通过 Path Casing 适配实现 100% 跨平台一致性**。
- **微内核架构 (v5.2)**：核心逻辑已完全迁移至 `file_cortex_core/` 包，支持作为库被第三方调用。
- **AI 上下文增强**：集成 **Token 实时估算 (FormatUtils)**、**Token 预算预警** 与 **Prompt 自动化模板**。
- **路径搜集预设 (v5.8)**：支持自定义文件前缀 (Prefix) 与 目录后缀 (Suffix)，内置 GPT/RAG 多套搜集预设。
- **高性能加载**：网页版支持目录懒加载、**自适应并发多线程搜索** 及 **二进制检测 Fast-path**。
- **ActionBridge 注入拦截 (v5.8)**：针对 Windows 环境下的环境变量注入 (`%`) 实施强制审计，提升 RCE 抵御能力。
- **智能化清单过滤 (v5.8)**：支持清单内容的实时搜索过滤与批量按类移除。
- **预览区内容检索 (v5.8)**：桌面端预览支持 `Ctrl+F` 高亮关键词查找。
- **ActionBridge 异步流 (Real-time Streaming)**：支持外部编排工具的 `stdout` 实时推送。
- **原子化持久化与自愈**：内核级项目配置 Schema 自动对齐、**线程安全单例模型 (RLock)** 及 原子化写入。
- **资源管理强化 (v5.8)**：强制回收搜索生成器任务，并在 Windows 测试环境下实现残留子进程递归杀伤。
- **标签化多重过滤 (v5.5)**：支持正向包含、反向排除及局部正则标签。
- **极速查重工具 (v5.5)**：引入 `DuplicateWorker`（后台线程），采用“大小预筛 + SHA256 哈希”策略。
- **非侵入式 UI 反馈 (v5.8)**：桌面端引入 Status Stream 机制，减少阻塞式 Messagebox 弹出。
- **工业级并发加固 (v5.8)**：DataManager 方法级原子锁、共享线程池优化，彻底杜绝高并发下的配置损坏。
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
