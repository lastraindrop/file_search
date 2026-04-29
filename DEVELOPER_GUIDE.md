# FileCortex - 开发者指南

> **版本**: 6.3.0 | **更新日期**: 2026-04-23

欢迎参与 FileCortex 的开发。本项目采用微内核架构，致力于构建一个本地优先、AI 友好的工作区编排工具。

---

## 1. 架构设计

### 1.1 配置管理 (SSOT)
`DataManager` 是系统的状态中心。v6.3.0 引入了 **Pydantic V2** 作为模型驱动。

*   **模型访问**: 推荐使用 `DataManager().config` 访问强类型对象。
*   **兼容性**: `.data` 属性提供字典视图，但不再支持直接赋值持久化。
*   **原子性**: 所有修改必须通过 `dm.update_*` 方法并调用 `dm.save()`。

### 1.2 核心模块
*   `file_cortex_core.security`: `PathValidator` 提供唯一性路径归一化协议。
*   `file_cortex_core.search`: 匹配逻辑与文件系统遍历已完全解耦。

---

## 2. 规范与标准 (Code Standards)

本项目严格执行 **Google Python Style Guide**。

### 2.1 自动化检查
开发者在提交代码前应运行以下工具：
1.  **Ruff**: `ruff check .` (强制执行 D, I, N, B, UP 等规则)。
2.  **Pytest**: `python -m pytest` (验证 191 项核心测试)。

### 2.2 Docstrings 样例
```python
def example_method(path: str) -> bool:
    """Example Google-style docstring.

    Args:
        path: Description of the input path.

    Returns:
        True if operation was successful.

    Raises:
        OSError: If file system access fails.
    """
```

---

## 3. 安全基线
*   **路径沙盒**: 所有外部路径输入必须通过 `PathValidator.is_safe`。
*   **注入防御**: `ActionBridge` 使用 `subprocess.run(list_args)` 避免 shell 注入风险。
*   **Token 审计**: 生产环境下所有 `/api/` 及 `/ws/` 请求均需通过 Token 校验。
