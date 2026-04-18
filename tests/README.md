# FileCortex - 自动化测试套件说明 (Test Suite)

本项目包含 **80** 项核心全自动化的 `pytest` 测试，采用 **领域驱动深度加固 (Domain-Driven Hardening)** 架构，实现了从底层 IO 到上层 API 契约的全方位覆盖。

## 🧪 测试分类 (Consolidated Architecture)

### 1. API 契约与回传分析 (`test_api_v6.py`)
- **深度契约校验**: 验证所有 API 返回对象包含 UI 所需的必备元数据。
- **Content Edge Cases**: 覆盖超大文件截断与二进制安全检测。
- **WebSocket 协议**: 验证搜索 WebSocket 实时流协议。

### 2. 核心工具与原子操作 (`test_core_integration.py`)
- **FileOps 隔离性**: 测试文件重命名回滚、项目项创建。
- **DuplicateWorker**: 验证后台查重任务的准确性。
- **NoiseReducer**: 验证噪音文件检测逻辑。

### 3. 配置持久化与 Schema 对齐 (`test_dm_config.py`)
- **自愈型 Schema**: 验证 DataManager 在读取过程中的自动补全逻辑。
- **分组管理**: 测试 Path Normalization 在 Windows/Unix 下的一致性。
- **并发安全**: 验证多线程下配置读写安全性。

### 4. 模式矩阵检索 (`test_search_engine.py`)
- **搜索参数对决**: 覆盖 Smart/Exact/Regex/Content 四大模式的所有逻辑组合。
- **Gitignore 合规**: 验证 .gitignore 忽略逻辑。
- **标签系统**: 验证 positive/negative 标签检索。

### 5. 路径安全与 Windows 并发加固 (`test_security_resilience.py`)
- **OS 并发鲁棒性**: 专项验证在高频写操作下通过 **Retry 机制** 解决 WinError 5。
- **Security Matrix**: 严密封锁 UNC 路径注入与 Directory Traversal。
- **ActionBridge 注入防御**: 验证命令注入安全防护。

### 6. 格式化与边界 (`test_utils_format.py`)
- **Size 格式化**: 验证字节单位转换 (B/KB/MB/GB)。
- **Token 估算**: 验证中日韩加权 Token 估算。
- **语言标签**: 验证文件扩展名到语言映射。

### 7. 上下文格式化 (`test_context_formatter.py`)
- **XML/Markdown 导出**: 验证 CDATA 转义与代码块嵌套。
- **Blueprint 生成**: 验证 ASCII 树状图生成。

### 8. 文件操作进阶 (`test_fileops_advanced.py`)
- **���子化保存**: 验证 tempfile 原子写入。
- **归档功能**: 验证 ZIP 打包。
- **批量重命名**: 验证 dry-run 模式。

### 9. Web 端点 (`test_web_endpoints.py`)
- **权限校验**: 验证系统目录拦截。
- **CORS**: 验证跨域请求处理。
- **暂存与设置**: 验证项目配置同步。

## 🚀 运行测试
在项目根目录下执行：
```powershell
python -m pytest
```

## 📋 测试环境要求
- Python 3.10+
- 所有依赖安装: `pip install -e ".[dev]"`
