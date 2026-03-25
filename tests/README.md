# AI Context Workbench - 测试套件说明 (Test Suite)

本项目包含 44 项全自动化的 `pytest` 测试，覆盖了核心逻辑、API 安全、桌面端交互及端到端流程。

## 🧪 测试分类

### 1. 核心逻辑测试 (`test_core_logic.py`)
- **路径校验**: 验证 `PathValidator` 是否能正确识别并拦截路径穿越攻击。
- **文件工具**: 测试 `is_binary`、`gitignore` 解析及 `Markdown` 格式化逻辑。
- **搜索引擎**: 验证 `smart` (关键词)、`regex` (正则)、`exact` (精确) 及内容搜索的正确性。
- **数据管理**: 测试 `DataManager` 的原子化写入、Schema 自动对齐及线程安全性。

### 2. Web API 安全测试 (`test_web_api.py`)
- **权限隔离**: 验证未注册路径是否被拦截。
- **WebSocket 搜索**: 测试搜索流的实时推送与断连处理。
- **文件操作**: 涵盖重命名、删除、归档等 API 的安全边界测试。

### 3. 桌面端安全测试 (`test_desktop_security.py`)
- **OS 调用安全**: 验证 PowerShell 系统剪切板复制时对恶意路径的过滤（防范 `Set-Clipboard -Path` 注入）。
- **进程隔离**: 确保跨平台路径打开逻辑的稳健性。

### 4. 端到端流程测试 (`test_e2e.py`)
- **完整链路**: 模拟从打开项目、扫描文件、加入清单到生成 AI 上下文的完整用户旅程。

## 🚀 运行测试

在项目根目录下执行：

```powershell
python -m pytest
```

### 进阶用法
- **显示详细信息**: `python -m pytest -v`
- **显示打印日志**: `python -m pytest -s`
- **运行特定模块**: `python -m pytest tests/test_core_logic.py`

## 🛠️ 测试环境要求
- **Python 3.8+**
- 依赖项: `pip install -r requirements.txt`
- **Mock 系统**: 测试框架使用了 `unittest.mock` 对文件系统和系统命令进行了隔离，无需特殊的物理磁盘配置即可运行。
