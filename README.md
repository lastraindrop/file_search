# FileCortex v6.2.0 Stable Release (工作区编排助手)

这是一个通用的 **工作区编排与文件处理工具 (Workspace Orchestrator)**。它可以帮助你高效地管理项目文件、通过 **Categorizer (分类器)** 整理目录、执行自动化脚本，并能一键导出结构化的上下文（支持 XML/Markdown）以供 AI 辅助编程使用。v6.2.0 版本引入了 **MCP Server 完整支持**、**XML 导出引擎**、**全局配置框架** 及 **80 项全量审计测试**。

## 🌟 核心理念
*   **Orchestration over Collection**: 从简单的"收集"进化为对工作区的"编排"。
*   **Agentic Era Ready**: 直接接入 AI 智能体生态 (MCP 协议)。

## 🌟 主要功能 (v6.2.0 Final)
- **AI 上下文对齐 (XML Export)**：实现了 **XML 导出引擎**（支持 CDATA 封装），大幅提升 LLM 对复杂/嵌套代码片段的解析精度。
- **项目蓝图 (Blueprint)**：一键生成项目架构 ASCII 快照，快速同步项目结构。
- **全局统一配置框架 (Unified Settings)**：引入了全局设置体系，彻底消除预览上限 (Preview Limit) 的硬编码。
- **MCP Server 标准化**：支持作为 **Model Context Protocol** 服务器运行，使 AI Agent (如 Claude Desktop) 能原生调用编排。提供 6 个工具：`search_files`, `get_file_context`, `list_workspaces`, `register_workspace`, `get_project_blueprint`, `get_file_stats`。
- **文件分类器 (Categorizer)**：三栏式 UI，支持自定义物理路径映射与跨项目安全移动。
- **80 项核心精简加固测试**：由五大模块整合而成，覆盖架构适配、多参数组合、并发竞争及 **API 深度契约对齐**。
- **极致 Web UX**：引入网页端自定义右键菜单、搜索防抖 (Debounce Search) 和全局快捷键辅助。
- **多端支持**：提供本地桌面版 (Tkinter) 和 现代网页版 (FastAPI)，**通过项目注册 (fctx open) 实现 100% 跨平台一致性**。
- **微内核架构**：核心逻辑已完全迁移至 `file_cortex_core/` 包，支持作为库被第三方调用。
- **AI 上下文增强**：集成 **中日韩加权 Token 估算 (FormatUtils)**、**Token 预算预警** 与 **Prompt 自动化模板**。
- **路径搜集预设**：支持自定义文件前缀 (Prefix) 与 目录后缀 (Suffix)，内置 GPT/RAG 多套搜集预设。
- **高性能加载**：网页版支持目录懒加载、**自适应并发多线程搜索** 及 **二进制检测 Fast-path**。
- **ActionBridge 指令加固**：自动识别 Windows 内置指令 (Echo/Dir)，支持环境变量转义 (`%%`)，彻底杜绝注入扩展风险。
- **智能化清单过滤器**：支持清单内容的实时搜索过滤与批量按类移除。
- **ActionBridge 异步流 (Real-time Streaming)**：支持外部编排工具的 `stdout` 实时推送。
- **原子化持久化与自愈**：内核级项目配置 Schema 自动对齐、**线程安全单例模型 (RLock)** 及 原子化写入。
- **安全路径监控**：UNC/网络路径拦截、AppleScript 注入拦截及基于白名单的 Settings 修改保护。
- **强制资源治理**：外部工具 300s 强制超时暗杀、Windows/Unix 树级进程清理以及 `os.scandir` 句柄自动回收机制。
- **极速查重工具**：引入 `DuplicateWorker`（后台线程），采用“大小预筛 + SHA256 哈希”策略。
- **内存安全与 OOM 防护**：采用流式编码探测与智能文本读取 (`read_text_smart`)。
- **工作区常驻与历史**：自动记录最近使用的 15 个项目，支持置顶 (Pin) 常用工作区。


## 📚 详细文档
- [开发者说明 (Architecture & Security)](DEVELOPER_GUIDE.md)
- [项目路线图 (Roadmap)](ROADMAP.md)
- [Pytest 测试说明](tests/README.md)

## 📐 代码规范

本项目遵循 **Google Python Style Guide**：

### 导入排序
```python
# 标准库
import os
import pathlib
import threading

# 第三方库
from fastapi import FastAPI
from pydantic import BaseModel

# 本地模块
from file_cortex_core import DataManager
```

### 类型注解
所有公共函数和方法均添加了完整的类型注解：
```python
def search_generator(
    root_dir: pathlib.Path,
    search_text: str,
    search_mode: str,
    manual_excludes: str,
    ...
) -> Generator[dict[str, Any], None, None]:
```

### Docstring 规范
所有公共类和方法均包含规范的 Google 风格文档字符串：
```python
def format_size(size_bytes: int) -> str:
    """Formats a byte size into human-readable string.

    Args:
        size_bytes: Size in bytes.

    Returns:
        Formatted size string (B, KB, MB, GB).
    """
```

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

- **50 核心全自动测试 (50 Core Automated Tests)**: `pytest` 全面覆盖。测试环境实现了 **DataManager 强制隔离重置**、**Windows 并发鲁棒性验证 (WinError 5)** 与 **进程树强制杀伤**：
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
