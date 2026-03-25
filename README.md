# AI Context Workbench (AI 上下文收集助手)

这是一个专为 AI 辅助编程设计的上下文收集工具。它可以帮助你快速扫描项目文件、生成 ASCII 树状结构，并将代码内容格式化为适合 AI 阅读的 Markdown 格式。

## 🌟 主要功能
- **多端支持**：提供本地桌面版 (Tkinter) 和 现代网页版 (FastAPI)，**真正支持 Windows/macOS/Linux 跨平台运行**。
- **高性能加载**：网页版支持目录懒加载及 **并发多线程搜索**，轻松处理万级文件项目。
- **智能搜索**：支持智能匹配、精确匹配、正则表达式匹配及全量并发内容搜索。
- **无状态架构**：Web API 采用完全无状态设计，支持浏览器多标签页同时操作不同项目。
- **工作区持久化**：自动保存待处理清单 (Staging) 及 收藏夹 (Favorites)，跨端同步工作进度。
- **项目树生成**：一键生成并复制整个项目的目录结构。
- **自动对齐与并发安全**：内核级项目配置 Schema 自动对齐、全局线程锁及原子化写入，杜绝数据损坏。
- **深度集成**：支持 `.gitignore` 规则及手动排除。
- **高安全性**：防范 XSS 攻击、路径穿越 (Path Traversal) 及 PowerShell 注入，严密保护系统目录。

## 📚 详细文档
- [开发者说明 (Architecture & Security)](DEVELOPER_GUIDE.md)
- [项目路线图 (Roadmap)](ROADMAP.md)
- [Pytest 测试报告](tests/README.md) *(暂未建立)*

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
项目包含 **44** 项覆盖核心逻辑、API、并发压力、安全及 E2E 的 `pytest` 跨平台测试：
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
