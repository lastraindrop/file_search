# FileCortex - 开发者指南

> **版本**: 6.2.0 | **更新日期**: 2026-04-21

欢迎参与 FileCortex 的开发。本文档详细介绍项目的架构设计、安全机制、开发规范和测试方法论。

---

## 目录
1. [架构设计](#1-架构设计)
2. [安全机制](#2-安全机制)
3. [核心模块](#3-核心模块)
4. [API 契约](#4-api-契约)
5. [测试方法论](#5-测试方法论)
6. [开发规范](#6-开发规范)
7. [贡献指南](#7-贡献指南)

---

## 1. 架构设计

### 1.1 整体架构

FileCortex 采用 **微内核 + 多端入口** 架构模式：

```
┌─────────────────────────────────────────────────────────────────┐
│                        用户入口层                                │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌────────┐ │
│  │ 桌面 GUI    │  │  Web UI     │  │   CLI       │  │ MCP    │ │
│  │(Tkinter)   │  │(FastAPI)    │  │ (fctx.py)  │  │ Server │ │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └───┬────┘ │
└─────────┼────────────────┼────────────────┼─────────────┼─────────────┘
          │                │                │             │
          ▼                ▼                ▼             ▼
┌─────────────────────────────────────────────────────────────────┐
│                      file_cortex_core (微内核)                   │
│  ┌──────────┐ ┌────────┐ ┌────────┐ ┌──────────┐ ┌──────┐  │
│  │ config  │ │ search │ │security│ │  utils  │ │actions│  │
│  └──────────┘ └────────┘ └────────┘ └──────────┘ └──────┘  │
└───────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────┐
│                       数据持久化层                                │
│             ~/.filecortex/config.json + logs/                      │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 核心设计原则

#### SSOT (Single Source of Truth)
所有路径权限及配置读取必须统一经过 `DataManager`。禁止直接读写文件系统或配置字典。

#### 契约自洽性
- **API 字段强校验**: 任何提供给前端的 API 对象（特别是搜索结果与文件元数据）**必须** 包含 UI 强依赖字段：`path`, `name`, `type`, `size_fmt`, `mtime_fmt`, `has_children`。
- **逻辑动态对齐**: 类似于预览上限、Token 预算、搜索默认参数等必须从 `global_settings` 或项目 `search_settings` 动态读取，禁止在代码中保留与 UI 不一致的硬编码。
- **交互入口一致**: 桌面 GUI、Web UI 与 CLI 的高频操作必须保持同等级可达性；例如“加入清单”不能只存在于某一个入口或依赖收藏中转。
- **类型安全**: 任何涉及长度、偏移或切片的操作必须在计算后执行 `int()` 显式转换。

#### Schema 自愈
`DataManager._apply_default_schema` 确保即使用户手动修改了配置文件或使用了旧版配置，系统也能自动补全缺失字段。

#### 路径归一化
所有外部路径（TreeView 选择、API 参数等）必须通过 `PathValidator.norm_path` 处理，强制执行 **小写化 + POSIX 斜杠** 转换。

### 1.3 模块职责

| 模块 | 职责 | 行数 |
|-----|------|------|
| `config.py` | DataManager 单例，配置持久化，Schema 管理 | ~500 |
| `security.py` | PathValidator 路径校验，黑名单拦截 | ~180 |
| `search.py` | SearchWorker 搜索，多线程并发 | ~400 |
| `utils.py` | FileUtils/FormatUtils/NoiseReducer | ~810 |
| `actions.py` | FileOps 文件操作，ActionBridge 命令执行 | ~560 |
| `duplicate.py` | DuplicateWorker 查重 | ~160 |

---

## 2. 安全机制

### 2.1 路径安全

#### 路径权限注册制
只有通过 `/api/open` 显式注册的目录才能作为 `project_root`。未注册的目录无法进行文件操作。

#### 黑名单保护
```python
SENSITIVE_DIRS = ['Windows', 'System32', 'System Volume Information']
PROTECTED_DIRS = ['.git', '.env', '.venv', 'node_modules']
```

#### UNC 路径拦截
识别 `\\server\share` 格式的 UNC 路径，防止 SMB 凭据泄露。

#### 路径归一化
使用 `PathValidator.norm_path` 消除符号链接和相对路径歧义。

### 2.2 命令执行安全

#### ActionBridge 安全策略
- **超时暗杀**: 所有外部工具执行 300s 强制超时。
- **白名单工具**: 仅执行已定义模板的工具。
- **参数转义**: 对环境变量使用 `%%` 转义，防止注入。
- **跨平台进程清理**: Windows 使用 `taskkill /F /T`，Unix 使用 `os.killpg`。

#### 注入防御示例
```python
# 错误的写法
os.system(f"git {user_input}")

# 正确的写法
subprocess.run(["git", user_input], shell=False)
```

### 2.3 API 安全

#### Token 认证
```bash
export FCTX_API_TOKEN="your_secret_token"
```

#### CORS 配置
```bash
export FCTX_ALLOWED_ORIGINS="https://example.com"
```

### 2.4 资源安全

#### 文件句柄管理
所有 `os.scandir` 调用必须使用 `with` 语句：
```python
with os.scandir(root) as entries:
    for entry in entries:
        # 处理条目
```

#### 并发控制
DataManager 使用 RLock 保护所有写操作，确保线程安全。

---

## 3. 核心模块

### 3.1 DataManager (config.py)

```python
class DataManager:
    """配置单例管理器

    Attributes:
        data: 内存中的配置数据
        config_path: 配置文件路径
        global_settings: 全局设置
    """
    
    _instance = None
    _lock = threading.RLock()
```

**核心方法**:
- `load()`: 从磁盘加载配置
- `save()`: 原子化写入配置
- `get_project_data(project_path)`: 获取项目配置
- `update_project_settings(project_path, settings)`: 更新设置

### 3.2 PathValidator (security.py)

```python
class PathValidator:
    """路径验证器
    
    提供安全的路径验证和归一化功能。
    """
    
    @staticmethod
    def is_safe(path: str, root: str) -> bool:
        """验证路径是否安全
        
        Args:
            path: 待验证的路径
            root: 项目根目录
            
        Returns:
            是否安全
        """
        
    @staticmethod
    def norm_path(path: str) -> str:
        """归一化路径
        
        返回标准化的路径字符串。
        """
```

### 3.3 SearchWorker (search.py)

```python
class SearchWorker:
    """文件搜索工作器
    
    支持多线程并发搜索和多种搜索模式。
    """
    
    def search(
        self,
        root_dir: str,
        query: str,
        mode: str = "smart",
        include_dirs: bool = False,
        case_sensitive: bool = False,
        is_inverse: bool = False,
        use_gitignore: bool = True,
        positive_tags: list[str] = None,
        negative_tags: list[str] = None,
        max_results: int = 1000,
    ) -> list[dict]:
        """执行搜索
        
        Args:
            root_dir: 搜索根目录
            query: 搜索关键词
            mode: 搜索模式 (smart|exact|regex|content)
            include_dirs: 是否包含目录
            case_sensitive: 是否大小写敏感
            is_inverse: 是否反向匹配
            use_gitignore: 是否使用 .gitignore
            positive_tags: 正向标签
            negative_tags: 反向标签
            max_results: 最大结果数
            
        Returns:
            搜索结果列表
        """
```

### 3.4 FileOps (actions.py)

```python
class FileOps:
    """文件操作工具
    
    提供安全的文件系统操作。
    """
    
    @staticmethod
    def move_file(src: str, dst_dir: str) -> str:
        """移动文件
        
        Args:
            src: 源文件路径
            dst_dir: 目标目录
            
        Returns:
            移动后的路径
        """
        
    @staticmethod
    def delete_file(path: str) -> None:
        """删除文件或目录
        
        Args:
            path: 目标路径
        """
```

### 3.5 ActionBridge (actions.py)

```python
class ActionBridge:
    """动作桥接器
    
    执行外部命令行工具。
    """
    
    @staticmethod
    def execute(
        template: str,
        file_path: str,
        project_root: str,
    ) -> subprocess.CompletedProcess:
        """执行工具
        
        Args:
            template: 命令模板
            file_path: 文件路径
            project_root: 项目根目录
            
        Returns:
            执行结果
        """
    
    @staticmethod
    def stream_tool(
        template: str,
        file_path: str,
        project_root: str,
    ) -> Generator[str, None, None]:
        """流式执行工具
        
        用于实时获取输出。
        """
```

---

## 4. API 契约

### 4.1 API 端点

| 端点 | 方法 | 描述 | 认证 |
|-----|------|------|------|
| `/api/open` | POST | 打开工作区 | 可选 |
| `/api/fs/children` | POST | 获取子文件 | 可选 |
| `/api/content` | GET | 获取文件内容 | 可选 |
| `/api/search` | WS | WebSocket 搜索 | 可选 |
| `/api/generate` | POST | 生成 AI 上下文 | 可选 |
| `/api/fs/move` | POST | 移动文件 | 可选 |
| `/api/fs/delete` | POST | 删除文件 | 可选 |
| `/api/config/global` | GET/POST | 全局配置 | Token |
| `/api/project/settings` | POST | 项目设置 | Token |
| `/api/project/note` | POST | 文件笔记 | Token |
| `/api/project/tag` | POST | 文件标签 | Token |

### 4.2 API 模型

#### FileNode
```python
class FileNode(BaseModel):
    """文件节点模型"""
    path: str
    name: str
    size: int
    size_fmt: str
    mtime: float
    mtime_fmt: str
    type: str  # "file" | "dir"
    has_children: bool = False
```

#### SearchRequest
```python
class SearchRequest(BaseModel):
    """搜索请求模型"""
    project_path: str  # 必须包含
    query: str
    mode: str = "smart"
    include_dirs: bool = False
    case_sensitive: bool = False
    is_inverse: bool = False
    use_gitignore: bool = True
    positive_tags: list[str] = []
    negative_tags: list[str] = []
    max_results: int = 1000
```

#### GenerateRequest
```python
class GenerateRequest(BaseModel):
    """生成请求模型"""
    project_path: str  # 必须包含
    files: list[str]
    export_format: str = "markdown"  # markdown | xml
    max_tokens: int = 100000
    include_patterns: list[str] = []
    exclude_patterns: list[str] = []
```

---

## 5. 测试方法论

### 5.1 测试结构

```
tests/
├── conftest.py              # pytest fixtures
├── test_dm_config.py      # DataManager 配置测试
├── test_security_*.py      # 安全测试
├── test_search_*.py        # 搜索测试
├── test_fileops_*.py       # 文件操作测试
├── test_web_*.py          # Web API 测试
├── test_utils_*.py        # 工具函数测试
├── test_context_*.py      # 上下文生成测试
└── test_comprehensive.py  # 综合测试
```

### 5.2 测试 Fixtures

```python
@pytest.fixture
def mock_project(tmp_path):
    """创建临时项目目录"""
    
@pytest.fixture
def clean_config(tmp_path):
    """创建干净的 DataManager 配置"""
    
@pytest.fixture
def api_client(tmp_path):
    """创建 FastAPI 测试客户端"""
```

### 5.3 运行测试

```bash
# 运行所有测试
python -m pytest

# 运行特定模块
python -m pytest tests/test_security_*.py -v

# 运行特定测试
python -m pytest tests/test_security_resilience.py::test_security_path_safe_relative -v
```

### 5.4 测试原则

- **隔离性**: 每个测试使用独立的 tmp_path
- **可重复性**: 测试结果必须可重复
- **清晰性**: 测试名称描述测试内容
- **完整性**: 覆盖正常路径和边界情况

---

## 6. 开发规范

### 6.1 代码风格

遵循 **Google Python Style Guide**：

```python
import os
import pathlib
import threading

from fastapi import FastAPI
from pydantic import BaseModel

from file_cortex_core import DataManager
```

### 6.2 类型注解

```python
def search_generator(
    root_dir: pathlib.Path,
    query: str,
    mode: str = "smart",
) -> Generator[dict[str, Any], None, None]:
```

### 6.3 Docstring

```python
def format_size(size_bytes: int) -> str:
    """Formats a byte size into human-readable string.

    Args:
        size_bytes: Size in bytes.

    Returns:
        Formatted size string (B, KB, MB, GB).

    Raises:
        ValueError: If size_bytes is negative.
    """
```

### 6.4 常量定义

```python
MAX_PREVIEW_SIZE = 1024 * 1024  # 1MB
DEFAULT_TIMEOUT = 300  # 5 minutes
```

### 6.5 错误处理

```python
try:
    result = risky_operation()
except ValueError as e:
    logger.error(f"Operation failed: {e}")
    raise HTTPException(status_code=400, detail=str(e)) from e
```

---

## 7. 贡献指南

### 7.1 提交准则

1. **KISS 原则**: 优先通过内置库解决问题。
2. **测试驱动**: 变更必须有对应的测试用例。
3. **契约自洽**: 变更 API 前先更新前端接收逻辑。
4. **防御性编程**: 对所有外部输入进行验证。

### 7.2 开发流程

1. Fork 项目
2. 创建功能分支
3. 实现功能和测试
4. 运行测试确保通过
5. 运行 `ruff check --fix .` 确保代码质量
6. Push 并创建 Pull Request

### 7.3 审查要点

- [ ] 功能正确性
- [ ] 安全性（路径校验、输入验证）
- [ ] 类型安全
- [ ] 测试覆盖
- [ ] 文档更新

---

## 📝 许可证
MIT License
