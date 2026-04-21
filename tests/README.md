# FileCortex - 自动化测试套件说明 (Test Suite)

> **测试数**: 160 | **状态**: All Passed | **Ruff**: 0 errors

本项目包含 **160** 项核心全自动化的 `pytest` 测试，采用 **领域驱动深度加固 (Domain-Driven Hardening)** 架构，实现了从底层 IO 到上层 API 契约、前端契约与桌面 GUI 动作约束的全方位覆盖。

---

## 📋 测试统计

| 模块 | 测试数 | 覆盖范围 |
|-----|-------|---------|
| test_api_v6.py | 12 | 浏览器契约、生成流程、WebSocket 协议 |
| test_comprehensive.py | 46 | 综合功能、参数边界、跨模块行为 |
| test_context_formatter.py | 6 | XML/MD 导出、Blueprint |
| test_core_integration.py | 11 | 核心集成、编码、查重 |
| test_dm_config.py | 7 | 配置持久化、Schema、并发 |
| test_fileops_advanced.py | 9 | 文件操作、归档、批量 |
| test_frontend_contract.py | 7 | 前端契约、目录树交互、GUI 动作约束 |
| test_mcp_server.py | 3 | MCP 工作区注册、上下文、统计 |
| test_search_engine.py | 10 | 多模式搜索、标签、Gitignore |
| test_security_resilience.py | 11 | 路径安全、注入防护、并发鲁棒性 |
| test_utils_format.py | 8 | 格式化、Token、语言 |
| test_web_api_advanced.py | 21 | API 契约、安全语义、全局设置 |
| test_web_endpoints.py | 9 | 端点边界与工作区行为 |
| **总计** | **160** | **100% 关键路径** |

---

## 🧪 测试分类

### 1. 配置与持久化 (`test_dm_config.py`)
- **单例与默认值**: 验证 DataManager 单例行为
- **Load/Save 对称性**: 配置读写一致性
- **并发压力**: 多线程配置写入安全性
- **分组管理**: 项目分组与路径归一化
- **分类器逻辑**: quick_categories 自动推荐
- **全局设置**: global_settings 读写

### 2. 路径安全与鲁棒性 (`test_security_resilience.py`)
- **路径验证矩阵**: 相对/绝对/UNC 路径安全
- **符号链接防护**: 路径遍历防护
- **注入防御**: 命令注入与 AppleScript 防护
- **资源泄漏审计**: 文件句柄泄漏检测
- **并发压力**: 10+ 线程并发测试
- **文件系统错误**: 权限错误处理

### 3. 搜索引擎 (`test_search_engine.py`)
- **搜索模式**: Smart/Exact/Regex/Content 四模式
- **参数矩阵**: 大小写/反向/忽略等组合
- **Gitignore 合规**: .gitignore 忽略逻辑
- **标签系统**: positive/negative 标签
- **结果限制**: max_results 边界与 stop 事件

### 4. 格式化工具 (`test_utils_format.py`)
- **Size 格式化**: B/KB/MB/GB/TB 转换
- **负数处理**: 负数边界处理
- **数字格式化**: 千分位与精度
- **日期时间**: 时区处理
- **Token 估算**: ASCII/CJK 加权
- **语言标签**: 扩展名到语言映射

### 5. 上下文生成 (`test_context_formatter.py`)
- **Markdown 导出**: 代码块格式化
- **XML 导出**: CDATA 转义
- **Blueprint 生成**: ASCII 树状图
- **噪音消除**: NoiseReducer 逻辑

### 6. 文件操作 (`test_fileops_advanced.py`)
- **原子化保存**: tempfile 原子写入
- **二进制拒绝**: 二进制文件检测
- **只读文件**: 权限错误处理
- **冲突处理**: 目标存在冲突
- **归档功能**: ZIP 打包
- **批量重命名**: Dry-run 模式

### 7. 核心集成 (`test_core_integration.py`)
- **编码识别**: UTF-8/GBK/Large 文件
- **二进制检测**: is_binary Fast-path
- **路径收集**: 相对/绝对模式
- **噪音消除**: 噪音文件检测
- **ActionBridge**: 外部工具执行
- **批量回滚**: 错误时自动回滚
- **查重**: DuplicateWorker

### 8. Web API (`test_web_*.py`)
- **浏览器合同**: FileNode 字段完整性
- **设置同步**: flat/nested 格式
- **项目元数据**: note/tag/工具/分类
- **文件操作**: move/rename/delete 安全
- **上下文生成**: Markdown/XML 导出
- **WebSocket**: 搜索实时流
- **Token 认证**: API 认证中间件

### 8.1 前端契约与 GUI 约束 (`test_frontend_contract.py`)
- **目录树交互**: 工作区打开后首层目录自动加载，保留深层懒加载
- **参数矩阵**: `include_dirs` / `case_sensitive` / `inverse` 等搜索参数保持前后端一致
- **OS 打开路径**: `/api/fs/open_os` 与前端调用保持一致
- **GUI 动作约束**: 桌面端必须允许从文件树直接添加到清单，禁止回退到硬编码图像处理器入口

### 9. 综合测试 (`test_comprehensive.py`)
- **DataManager 高级**: 分页/置顶/白名单
- **PathValidator 高级**: UNC/敏感目录
- **SearchWorker 高级**: 内容搜索/Regex
- **FileOps 高级**: 批量操作
- **ActionBridge**: 工具执行
- **DuplicateWorker**: 查重
- **Utils 高级**: 路径收集/Blueprint

---

## 🚀 运行测试

### 运行所有测试
```bash
python -m pytest
```

### 运行特定模块
```bash
python -m pytest tests/test_security_resilience.py -v
python -m pytest tests/test_search_engine.py -v
python -m pytest tests/test_web_api_*.py -v
```

### 运行特定测试
```bash
python -m pytest tests/test_security_resilience.py::test_security_path_safe_relative -v
```

### 测试覆盖率
```bash
python -m pytest --cov=file_cortex_core --cov-report=term-missing
```

---

## 🛠 测试开发指南

### 创建新测试
```python
def test_new_feature(mock_project):
    """测试描述"""
    # Arrange
    ...
    # Act
    result = ...
    # Assert
    assert result == expected
```

### 测试 Fixtures
```python
@pytest.fixture
def mock_project(tmp_path):
    """创建临时项目"""
    
@pytest.fixture
def clean_config(tmp_path):
    """干净的 DataManager"""
    
@pytest.fixture
def api_client(tmp_path):
    """FastAPI 测试客户端"""
```

### 测试原则
1. **隔离性**: 使用 tmp_path 隔离
2. **可重复**: 每次运行结果一致
3. **清晰性**: 名称描述测试内容
4. **完整性**: 覆盖边界情况

---

## 📋 测试环境要求

- Python 3.10+
- pytest 8.0+
- 所有依赖: `pip install -r requirements.txt`

---

## ✅ 验收清单

- [x] 160 tests passed
- [x] 0 failed
- [x] Ruff 0 errors
- [x] Windows 并发通过
- [x] 测试隔离有效

---

## 📝 许可证
MIT License
