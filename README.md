# FileCortex v6.2.0 Stable Release (工作区编排助手)

> **版本**: 6.2.0 | **测试**: 143 passed | **代码质量**: Ruff 0 errors

这是一个通用的 **工作区编排与文件处理工具 (Workspace Orchestrator)**。它可以帮助你高效地管理项目文件、通过 **Categorizer (分类器)** 整理目录、执行自动化脚本，并能一键导出结构化的上下文（支持 XML/Markdown）以供 AI 辅助编程使用。v6.2.0 版本引入了 **MCP Server 完整支持**、**XML 导出引擎**、**全局配置框架** 及 **143 项全量审计测试**。

## 🌟 核心理念
- **Orchestration over Collection**: 从简单的"收集"进化为对工作区的"编排"。
- **Agentic Era Ready**: 直接接入 AI 智能体生态 (MCP 协议)。

## 🌟 主要功能 (v6.2.0 Final)

### AI 上下文增强
- **XML 导出引擎**：实现了 **XML 导出引擎**（支持 CDATA 封装），大幅提升 LLM 对复杂/嵌套代码片段的解析精度。
- **项目蓝图 (Blueprint)**：一键生成项目架构 ASCII 快照，快速同步项目结构。
- **中日韩 Token 加权估算**：集成 **FormatUtils** 的 CJK 加权 Token 估算，自动识别中日韩文字并应用正确的权重计算。
- **Token 预算预警**：UI 会在超过阈值时通过颜色警示用户。

### 多端访问
- **桌面版 (Tkinter)**：原生桌面体验，支持目录树导航与实时预览。
- **网页版 (FastAPI)**：现代 Web UI，支持自定义右键菜单、搜索防抖和全局快捷键。
- **CLI 工具 (fctx.py)**：headless 环境下的命令行编排，支持 `open`, `stage` 等命令。
- **MCP Server**：作为 **Model Context Protocol** 服务器运行，使 AI Agent 能原生调用。

### 文件管理
- **多模式搜索**：支持 smart（智能）、exact（精确）、regex（正则）、content（内容）四种搜索模式。
- **标签系统**：positive/negative 标签，支持多维度筛选。
- **批量操作**：批量重命名 (Regex)、批量删除、批量归档 (ZIP)。
- **查重工具**：DuplicateWorker 使用 "大小预筛 + SHA256" 策略。

### 安全加固
- **路径权限注册制**：只有通过 `/api/open` 显式注册的目录才能作为 `project_root`。
- **黑名单保护**：拦截 `Windows`, `System32`, `.git`, `.env` 等系统及敏感目录。
- **UNC 路径拦截**：识别并拦截 Windows UNC 路径（如 `\\server\share`）。
- **注入防御**：ActionBridge 增加了对 AppleScript 指令的双引号转义防护。
- **API Token 认证**：通过环境变量 `FCTX_API_TOKEN` 进行 API 认证。
- **CORS 中间件**：支持跨域请求（可通过 `FCTX_ALLOWED_ORIGINS` 配置）。

### 性能优化
- **并发搜索**：ThreadPoolExecutor 并发扫描，智能线程池调度。
- **懒加载**：Web 版支持目录懒加载。
- **二进制 Fast-path**：is_binary 快速路径检测。
- **强制超时暗杀**：所有外部工具执行 300s 强制超时。

### 数据持久化
- **原子化写入**：tempfile.NamedTemporaryFile + os.replace，线程安全。
- **Schema 自愈**：配置字段热补全，自动合并 DEFAULT_SCHEMA。
- **工作区常驻**：自动记录最近使用的 15 个项目，支持 Pin 置顶。

---

## 📚 详细文档
- [开发者说明 (Architecture & Security)](DEVELOPER_GUIDE.md)
- [项目路线图 (Roadmap)](ROADMAP.md)
- [全面分析报告](ANALYSIS_REPORT.md)
- [综合开发计划](COMPREHENSIVE_PLAN.md)
- [Pytest 测试说明](tests/README.md)

---

## 🚀 快速开始

### 环境要求
- Python 3.9+
- Windows/macOS/Linux

### 桌面版
```bash
# 安装依赖
pip install -r requirements.txt

# 运行桌面版
python file_search.py
```

### 网页版
```bash
# 运行 Web 服务器
python web_app.py

# 浏览器访问
http://127.0.0.1:8000
```

### CLI 工具
```bash
# 注册当前目录为工作区
python fctx.py open .

# 查看工作区列表
python fctx.py workspaces

# 搜索文件
python fctx.py search main.py --mode smart
```

### MCP Server
```bash
# 启动 MCP 服务
python mcp_server.py --transport stdio
```

---

## 🧪 测试

### 运行所有测试
```bash
python -m pytest
```

### 测试覆盖
- **143 项核心测试**：涵盖 API 契约、核心工具、配置、搜索、安全鲁棒性、格式化等。
- **测试结果**：143 passed, 0 failed

### 代码质量检查
```bash
# Ruff 静态分析
python -m ruff check .

# 自动修复
python -m ruff check . --fix
```

---

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

### 快速格式化
```bash
pip install isort ruff black
isort .
ruff check --fix .
black .
```

---

## 📂 项目结构

```
file_cortex_core/          # 微内核逻辑包
├── __init__.py           # 导出接口
├── config.py            # DataManager 单例与配置
├── security.py         # PathValidator 路径校验
├── utils.py           # FileUtils, FormatUtils, NoiseReducer
├── actions.py        # FileOps, ActionBridge
├── search.py        # SearchWorker, search_generator
├── duplicate.py    # DuplicateWorker 查重

file_search.py           # Tkinter 桌面版
web_app.py              # FastAPI Web 版
fctx.py                # CLI 工具
mcp_server.py          # MCP 协议服务器

tests/                  # 测试套件 (143 tests)
├── conftest.py        # pytest fixtures
├── test_*.py         # 各模块测试

static/                  # Web 静态资源
templates/               # HTML 模板

build_exe.py            # PyInstaller 打包脚本
requirements.txt        # 依赖清单
```

---

## 🛠 开发与部署

### 依赖安装
```bash
pip install -r requirements.txt
```

### 重新打包 EXE
```bash
python build_exe.py
```

### 环境变量
| 变量 | 说明 | 默认值 |
|-----|------|-------|
| FCTX_API_TOKEN | API 认证 Token | (无) |
| FCTX_ALLOWED_ORIGINS | 允许的跨域来源 | * |
| FCTX_PORT | Web 服务端口 | 8000 |

---

## 📝 许可证
MIT License

---

## 🔗 相关链接
- GitHub: https://github.com/anomalyco/filecortex
- 文档: https://filecortex.ai