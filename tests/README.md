# FileCortex - 自动化测试套件说明 (Test Suite)

本项目包含 **50** 项核心全自动化的 `pytest` 测试，采用 **领域驱动深度加固 (Domain-Driven Hardening)** 架构，实现了从底层 IO 到上层 API 契约的全方位覆盖。

## 🧪 测试分类 (Consolidated Architecture)

### 1. API 契约与回传分析 (`test_api_v6.py`)
- **深度契约校验**: 验证所有 API 返回对象包含 UI 所需的必备元数据。
- **Content Edge Cases**: 覆盖超大文件截断与二进制安全检测。

### 2. 核心工具与原子操作 (`test_core_integration.py`)
- **FileOps 隔离性**: 测试文件重命名回滚、项目项创建。
- **DuplicateWorker**: 验证后台查重任务的准确性。

### 3. 配置持久化与 Schema 对齐 (`test_dm_config.py`)
- **自愈型 Schema**: 验证 DataManager 在读取过程中的自动补全逻辑。
- **分组管理**: 测试 Path Normalization 在 Windows/Unix 下的一致性。

### 4. 模式矩阵检索 (`test_search_engine.py`)
- **搜索参数对决**: 覆盖 Smart/Exact/Regex/Content 四大模式的所有逻辑组合。

### 5. 路径安全与 Windows 并发加固 (`test_security_resilience.py`)
- **OS 并发鲁棒性**: 专项验证在高频写操作下通过 **Retry 机制** 解决 WinError 5。
- **Security Matrix**: 严密封锁 UNC 路径注入与 Directory Traversal。

## 🚀 运行测试
在项目根目录下执行：
```powershell
python -m pytest
```
