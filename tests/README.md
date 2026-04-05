# FileCortex - 自动化测试套件说明 (Test Suite)

本项目包含 **177** 项全自动化的 `pytest` 测试，采用 **微内核一对一镜像测试** 架构，实现了对核心逻辑、API 安全、及 AI 编排工作流的全方位覆盖。

## 🧪 测试分类 (Modular Architecture)

### 1. 核心引擎测试 (file_cortex_core 镜像)
- **搜索引擎 (`test_search.py`)**: 采用 **参数矩阵 (Matrix Testing)** 覆盖了 Smart/Exact/Regex/Content 模式。
- **安全检查 (`test_security.py`)**: 验证 `PathValidator` 的路径组件匹配机制。
- **系统工具 (`test_utils.py`)**: 特色功能测试，包括 **Token 估算准确度**、搜集符号注入等。
- **配置一致性 (`test_config.py`)**: 验证 `DataManager` 的原子写入、RLock 并发保护。
- **物理操作 (`test_actions.py`)**: 测试 `FileOps` 隔离性及 `ActionBridge` 的 **环境变量注入审计 (v5.8)**。

### 2. Web API 接入测试 (`test_web_api.py`)
- **权限与审计**: 验证所有 API 的 `get_valid_project_root` 拦截效果。
- **交互流程**: 涵盖 WebSocket 搜索流、文件操作。

### 3. 桌面端特化测试 (`test_desktop_security.py`)
- **命令注入防护**: 针对 Windows PowerShell `Set-Clipboard` 的参数化调用防御测试。

### 4. 生产稳定性测试 (v5.8 Hardening)
- **并发压力测试 (`test_stress_concurrency.py`)**: 验证高负载下的配置原子性。
- **环境安全测试 (`test_audit_fixes_v58.py`)**: 专项验证符号注入拦截。
- **沙箱隔离验证**: 确保在 Windows 环境下残留进程被递归杀伤 (`conftest.py`)。

## 🚀 运行测试

在项目根目录下执行：

```powershell
python -m pytest
```

## 🛡️ 设计准则：动态对齐 (Dynamic Alignment)
本项目的所有测试均遵循 **“零硬编码”** 原则，确保在任何宿主环境（Windows/Unix）下的逻辑路径、权限校验及并发控制均能实现镜像对齐。

