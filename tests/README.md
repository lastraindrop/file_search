# FileCortex - 自动化测试套件说明 (Test Suite)

本项目包含 **60+** 项全自动化的 `pytest` 测试，采用 **微内核一对一镜像测试** 架构，实现了对核心逻辑、API 安全、及 AI 编排工作流的全方位覆盖。

## 🧪 测试分类 (Modular Architecture)

### 1. 核心引擎测试 (file_cortex_core 镜像)
- **搜索引擎 (`test_search.py`)**: 采用 **参数矩阵 (Matrix Testing)** 覆盖了 Smart/Exact/Regex/Content 模式、正反向、大小写及 .gitignore 规则的笛卡尔积组合。
- **安全检查 (`test_security.py`)**: 验证 `PathValidator` 的路径组件匹配机制，拦截针对 Windows/Unix 系统目录的越权访问。
- **系统工具 (`test_utils.py`)**: 特色功能测试，包括 **Token 估算准确度**、二进制文件识别 (Fast-path) 及 AI 上下文渲染。
- **配置一致性 (`test_config.py`)**: 验证 `DataManager` 的原子写入、Schema 自动补全及线程并发锁机制。
- **物理操作 (`test_actions.py`)**: 测试 `FileOps` 的隔离性及 `ActionBridge` 的跨平台命令转义安全。

### 2. Web API 接入测试 (`test_web_api.py`)
- **权限与审计**: 验证所有 API 的 `get_valid_project_root` 拦截效果，并核对审计日志输出。
- **交互流程**: 涵盖 WebSocket 搜索流、文件重命名/删除/归档等核心接口。

### 3. 桌面端特化测试 (`test_desktop_security.py`)
- **命令注入防护**: 针对 Windows PowerShell `Set-Clipboard` 的参数化调用防御测试。

### 4. 端到端流程测试 (`test_e2e.py`)
- **AI 编排流**: 模拟“打开项目 -> 检索发现 -> 暂存清单 -> 渲染上下文”的完整应用逻辑。

## 🚀 运行测试

在项目根目录下执行：

```powershell
python -m pytest
```

### 进阶用法
- **显示详细矩阵**: `python -m pytest -v` (推荐，可看到所有参数组合的执行情况)
- **打印运行时日志**: `python -m pytest -s`
- **运行特定引擎测试**: `python -m pytest tests/test_search.py`

## 🛡️ 设计准则：动态对齐 (Dynamic Alignment)
本项目的所有测试均遵循 **“零硬编码”** 原则：
- **路径感知**: 严禁在测试中出现驱动器号或硬编码分隔符。
- **环境隔离**: 使用 `tmp_path` 为每个用例创建独立的物理沙箱，确保测试可并发运行且不污染宿主环境。
