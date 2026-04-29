# FileCortex v6.3.0 Production Ready (工作区编排助手)

> **版本**: 6.3.0 | **测试**: 191 passed | **代码质量**: Ruff 0 errors

## 🌟 核心理念
- **Orchestration over Collection**: 从简单的"收集"进化为对工作区的"编排"。
- **Engineering Excellence**: 基于 **Pydantic V2** 与 **Google Style** 构建的健壮内核。

## 🌟 主要功能 (v6.3.0 Final)
...
- **强类型配置**: 引入 Pydantic 模型驱动的 `DataManager`，实现配置的自愈与严谨校验。
- **策略化搜索**: 重构后的搜索引擎支持多维度匹配策略，更易于扩展。

### 现代化交互
- **控制中心 (Control Center)**: Web 端引入顶部全局过滤器工具栏，统一配置“排除规则”与“搜索模式”，实现流程驱动的沉浸式体验。
- **智能查重 (Smart Cleanup)**: DuplicateFinder 支持“保留最早/最晚”一键筛选冗余文件，效率提升 10x。
- **XML 导出引擎**: 实现了 **XML 导出引擎**（支持 CDATA 封装），大幅提升 LLM 对复杂/嵌套代码片段的解析精度。
- **项目蓝图 (Blueprint)**: 一键生成项目架构 ASCII 快照，快速同步项目结构。

### 性能与安全
- **二级探测缓存**: 引入 `(path, mtime, size)` 编码探测缓存，大幅提升大规模文件读取速度。
- **内存防溢出**: 针对并发内容搜索实施了 `max_bytes` 物理隔离，确保低配机器也能流畅运行。
- **路径沙盒**: 强化后的 `PathValidator` 确保跨平台路径 Key 的唯一性与安全性。
- **Token 预算预警**: UI 会在超过阈值时通过颜色警示用户。

### 多端访问
- **桌面版 (Tkinter)**：原生桌面体验，支持目录树导航与实时预览。
- **网页版 (FastAPI)**：现代化 ES6 模块化前端，支持自定义右键菜单、搜索防抖和全局快捷键。
- **CLI 工具 (fctx.py)**：Headless 环境下的命令行编排，支持 `open`, `stage`, `run` 等命令。
- **MCP Server**：作为 **Model Context Protocol** 服务器运行，支持 AI Agent 原生调用。

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
- Python 3.10+
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
- **191 项核心测试**：涵盖内核逻辑、安全沙盒、API 契约、搜索矩阵、WebSocket 实时流、前端模块化契约及 Windows 兼容性全量审计。
- **测试结果**：191 passed, 0 failed

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
├── __init__.py           # 统一接口导出
├── config.py            # DataManager (SSOT 配置中心)
├── security.py         # PathValidator (安全沙盒与归一化)
├── file_io.py          # FileUtils (物理 I/O 与 Gitignore)
├── format_utils.py     # FormatUtils (格式化与 Token 估算)
├── context.py          # ContextFormatter (AI 上下文导出)
├── search.py           # SearchWorker (搜索引擎)
├── actions.py          # FileOps, ActionBridge (执行桥接)
├── gui/                # 抽离的 GUI 组件 (BatchRename, DuplicateFinder)
├── duplicate.py        # DuplicateWorker (SHA256 查重)

routers/                  # 模块化路由层
├── http_routes.py      # 标准 HTTP 端点
├── ws_routes.py        # 实时搜索 WebSocket
├── services.py         # 业务逻辑服务层 (Service Layer)
├── schemas.py          # Pydantic 参数校验模型 (Schema Layer)
└── common.py           # 共享状态与进程管理

static/js/                # 模块化前端 (ES6 Modules)
├── main.js             # 流程控制
├── state.js            # 状态中心
├── api.js              # API 封装
└── ui.js               # UI 渲染驱动

file_search.py           # Tkinter 桌面版 (轻量化 Controller)
web_app.py              # FastAPI Web 入口
fctx.py                # CLI 工具入口
mcp_server.py          # MCP 协议服务入口

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
pip install .[build]
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
