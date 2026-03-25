# AI Context Workbench (AI 上下文收集助手)

这是一个专为 AI 辅助编程设计的上下文收集工具。它可以帮助你快速扫描项目文件、生成 ASCII 树状结构，并将代码内容格式化为适合 AI 阅读的 Markdown 格式。

## 🌟 主要功能
- **多端支持**：提供本地桌面版 (Tkinter) 和 现代网页版 (FastAPI)，**真正支持 Windows/macOS/Linux 跨平台运行**。
- **高性能加载**：网页版支持目录懒加载及 **自适应并发多线程搜索**，显著提升高负载下的吞吐效率。
- **上下文增强**：生成的 Markdown 头部自动包含文件元数据（如 `(1.2 KB)`），帮助 AI 更好地理解上下文的时效性。
- **操作审计 (Audit Log)**：Web API 记录所有敏感操作（如删除、保存），实现零信任环境下的行为可追溯。
- **一键路径复制**：Web 界面新增“Copy Path”功能，支持直观的文件路径分发。
- **无状态架构**：Web API 采用完全无状态设计，支持浏览器多标签页同时操作不同项目。
- **工作区持久化**：自动保存待处理清单 (Staging) 及 收藏夹 (Favorites)，跨端同步工作进度。
- **自动对齐与并发安全**：内核级项目配置 Schema 自动对齐、全局线程锁及原子化写入，实现旧版数据的“自愈”升级。
- **高安全性**：防范 XSS 攻击、路径穿越 (Path Traversal) 及 PowerShell 注入，严密保护系统目录。

## 📚 详细文档
- [开发者说明 (Architecture & Security)](DEVELOPER_GUIDE.md)
- [项目路线图 (Roadmap)](ROADMAP.md)
- [Pytest 测试说明](tests/README.md)

## 🚀 快速开始

### 桌面版 (直接运行)
- **已打包用户**：下载并解压，双击 `dist/AI_Context_Workbench.exe`。
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

## 🧪 测试
项目包含 **44+** 项覆盖核心逻辑、API、并发压力、安全及 E2E 的 `pytest` 测试。采用 **“零硬编码”架构**，支持跨平台自适应运行：
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
- `core_logic.py`: 核心业务逻辑（搜索、扫描、统计）。
- `file_search.py`: Tkinter 桌面端应用。
- `web_app.py`: FastAPI Web 应用。
- `tests/`: 自动化测试套件（Core, API, E2E）。
- `static/` & `templates/`: Web 静态资源与模板。
- `build_exe.py`: 自动化打包脚本。

## 📝 许可证
MIT License
