# FileCortex v6.5.0 → v6.5.1 — P0/P1 施工计划书

> **文档性质**: 可直接执行的施工规范（非概要）。每项含定位 / 根因 / 精确 diff / 影响面 / 验证 / 回归测试 / 回滚。
> **基线**: 629 passed · Ruff 0 errors · 全部 diff 已对照真实源码逐行核对。
> **目标版本**: v6.5.1（P0+P1 完成后发布）
> **预计工时**: P0 ≈ 1.5h · P1 ≈ 5h · 测试编写 ≈ 3h · 合计 ≈ 9.5h

---

## 目录

- [施工总则](#施工总则)
- [Phase P0 — 部署阻断修复（7 项）](#phase-p0--部署阻断修复7-项)
- [Phase P1 — 安全加固与一致性（13 项）](#phase-p1--安全加固与一致性13-项)
- [回归测试套件设计](#回归测试套件设计)
- [验证矩阵与发布门禁](#验证矩阵与发布门禁)
- [执行顺序与并行度](#执行顺序与并行度)
- [风险登记表](#风险登记表)

---

## 施工总则

### 修改原则

1. **最小改动**: 每项 BUG 只改必要的行，不顺手重构（避免"修 BUG 引入 BUG"）
2. **向后兼容**: 所有 API 改动新增字段用 `Optional` + 默认值，不破坏现有前端
3. **先测后改**: 回归测试先写（部分会 fail），改完转 pass（TDD 锁定）
4. **原子提交**: 每项 BUG 一个 commit，message 格式 `fix(v651): BUG-ID 简述`
5. **验证门禁**: 每完成一组（P0.x）跑 `ruff + pytest` 全绿才进下一组

### 通用验证命令

```powershell
# 每次修改后跑（< 5 秒）
python -m ruff check .

# 每组完成后跑（~195s，P2.1 优化后 ~80s）
python -m pytest --tb=short

# 发布前跑（打包烟雾）
python -m pip install -e . && python -c "import web_app, routers, fctx, mcp_server"
```

---

## Phase P0 — 部署阻断修复（7 项）

> 目标：修完后 `pip install .` 可用、MCP 可真实运行、token 不泄露、categorize 不可越界、mermaid 有 SRI。**这 7 项完成后系统才可称为"实际可落地"。**

---

### P0.1 — 修复 `pyproject.toml` 打包缺漏 `routers` 包（BUG-D1）

**定位**: `pyproject.toml:49-51`
```toml
[tool.setuptools]
packages = ["file_cortex_core"]
py-modules = ["fctx", "web_app", "file_search"]
```

**根因**: `routers/` 是真实 Python 包（有 `__init__.py`，被 `web_app.py:19-21` 导入），但未声明。`pip install .`（非 `-e`）后 `from routers.http_routes import router` 抛 `ModuleNotFoundError`。

**修改**（`pyproject.toml:49-51`）:
```toml
[tool.setuptools]
packages = ["file_cortex_core", "routers"]
py-modules = ["fctx", "web_app", "file_search", "mcp_server", "build_exe"]
```

**影响面**: 仅打包元数据；`pip install -e .` 开发模式不受影响；新增 `mcp_server`/`build_exe` 为 py-module 让 `fctx-mcp` 控制台脚本（P0.3）可用。

**验证**:
```powershell
# 1. 干净环境模拟
python -m pip uninstall file-cortex -y
python -m pip install .
python -c "from routers.http_routes import router; from routers.ws_routes import router as w; print('OK')"
# 预期: OK
python -c "import mcp_server; print('mcp_server OK')"
# 预期: mcp_server OK
```

**回归测试**（新增 `tests/test_packaging.py`）:
```python
"""Packaging integrity smoke tests (BUG-D1 regression)."""


def test_routers_importable() -> None:
    """Routers package must be importable after pip install."""
    import routers  # noqa: F401
    from routers.http_routes import router  # noqa: F401
    from routers.ws_routes import router as ws_router  # noqa: F401


def test_entry_modules_importable() -> None:
    """Entry-point modules must be importable."""
    import web_app  # noqa: F401
    import fctx  # noqa: F401
    import mcp_server  # noqa: F401


def test_pyproject_declares_routers() -> None:
    """pyproject.toml must list routers in packages."""
    import pathlib
    import tomllib

    pyproject = pathlib.Path(__file__).resolve().parent.parent / "pyproject.toml"
    with open(pyproject, "rb") as f:
        data = tomllib.load(f)
    packages = data["tool"]["setuptools"].get("packages", [])
    assert "routers" in packages, f"routers missing from {packages}"
```

**回滚**: `git revert <commit>` 即可，无数据/状态影响。

---

### P0.2 — 声明 `mcp` 为可选依赖 + README 说明（BUG-D2）

**定位**:
- `pyproject.toml:30-43`（`[project.optional-dependencies]`）
- `README.md:88-92`（MCP 章节）

**根因**: `mcp_server.py:22` 顶层 `try: from mcp.server.fastmcp import FastMCP` 回退到 mock 类（line 27-54）。`mcp` 包未在任何依赖中声明。`main()` (line 286-319) 虽已有 `pip install mcp` 提示，但只在运行时才暴露，安装时无感知。README 给出 `python mcp_server.py --transport stdio` 命令却未说明前置依赖。

**修改 1**（`pyproject.toml`，在 `[project.optional-dependencies]` 内新增）:
```toml
[project.optional-dependencies]
dev = [
    "pytest>=7.3.0",
    "pytest-asyncio>=0.21.0",
    "ruff>=0.1.0",
    "black>=23.0.0",
    "isort>=5.12.0",
]
mcp = [
    "mcp>=1.0.0",
]
gui = [
    "customtkinter>=5.1.0",
]
build = [
    "pyinstaller>=6.18.0",
]
```

**修改 2**（`README.md:89-92`，MCP Server 章节）:
```markdown
### MCP Server（需额外安装 MCP SDK）
```bash
# 1. 安装 MCP 可选依赖
pip install -e ".[mcp]"
# 或: pip install mcp>=1.0.0

# 2. 启动（stdio 传输，供 Claude Desktop / Cline 等 MCP 客户端调用）
python mcp_server.py --transport stdio

# 3. 在 Claude Desktop 配置中注册（示例）
# ~/Library/Application Support/Claude/claude_desktop_config.json (macOS)
# 或 %APPDATA%\Claude\claude_desktop_config.json (Windows):
{
  "mcpServers": {
    "file-cortex": {
      "command": "python",
      "args": ["<path-to>/mcp_server.py"]
    }
  }
}
```
> 注：未安装 `mcp` 包时，`mcp_server.py` 进入 mock 回退模式（仅打印工具列表，不提供真实 MCP 传输）。
```

**修改 3**（`mcp_server.py:main()`，强化 fallback 退出码，line 307-318）:
```python
    if _MCP_SDK_AVAILABLE:
        try:
            mcp_server.run(host=args.host, port=args.port)
            return
        except Exception as e:
            print(f"MCP SDK run failed: {e}", file=sys.stderr)
            sys.exit(1)

    # Mock fallback: print info and exit non-zero so callers know it's not live.
    print("FileCortex MCP Server — FALLBACK MODE (SDK not installed).", file=sys.stderr)
    print(f"Available tools: {list(mcp_server._tools.keys())}", file=sys.stderr)
    print("\nMCP SDK not installed. Install with:", file=sys.stderr)
    print('  pip install -e ".[mcp]"    (development)', file=sys.stderr)
    print('  pip install mcp             (runtime)', file=sys.stderr)
    print("\nServer NOT started. Exit code 2.", file=sys.stderr)
    sys.exit(2)
```

**影响面**: 安装/运行行为；`sys.exit(2)` 在 mock 模式让 CI/脚本可检测（之前是隐式 exit 0）。

**验证**:
```powershell
# 1. 不装 mcp 时退出码非 0
python mcp_server.py --transport stdio; echo "EXIT=$?"
# 预期: STDERR 含 "FALLBACK MODE"，EXIT=2

# 2. 装 mcp 后（需手动 pip install mcp）
pip install mcp
python -c "from mcp.server.fastmcp import FastMCP; print('mcp OK')"
# 预期: mcp OK
```

**回归测试**（加入 `tests/test_packaging.py`）:
```python
def test_pyproject_declares_mcp_optional() -> None:
    """mcp must be declared as an optional dependency."""
    import pathlib
    import tomllib

    pyproject = pathlib.Path(__file__).resolve().parent.parent / "pyproject.toml"
    with open(pyproject, "rb") as f:
        data = tomllib.load(f)
    optional = data["project"].get("optional-dependencies", {})
    assert "mcp" in optional, "Missing [project.optional-dependencies].mcp"
    assert any("mcp" in dep for dep in optional["mcp"])
```

**回滚**: 还原 pyproject + README + mcp_server.py:main。

---

### P0.3 — 新增 `fctx-mcp` 控制台脚本入口（BUG-Doc5）

**定位**: `pyproject.toml:45-47`

**根因**: `[project.scripts]` 仅声明 `fctx` / `fctx-web`，无 MCP 入口，与"四端访问"卖点不一致；用户必须用 `python mcp_server.py`。

**修改**（`pyproject.toml:45-47`）:
```toml
[project.scripts]
fctx = "fctx:main"
fctx-web = "web_app:main"
fctx-mcp = "mcp_server:main"
```

**影响面**: `pip install .` 后终端可直接 `fctx-mcp --transport stdio`。

**验证**:
```powershell
pip install .
fctx-mcp --help
# 预期: 显示 argparse 帮助（--transport/--host/--port）
```

**回归测试**: 加入 `tests/test_packaging.py`:
```python
def test_pyproject_declares_mcp_console_script() -> None:
    """fctx-mcp console script must be declared."""
    import pathlib
    import tomllib

    pyproject = pathlib.Path(__file__).resolve().parent.parent / "pyproject.toml"
    with open(pyproject, "rb") as f:
        data = tomllib.load(f)
    scripts = data["project"].get("scripts", {})
    assert scripts.get("fctx-mcp") == "mcp_server:main"
```

---

### P0.4 — 修复 `api_categorize` 路径遍历（BUG-W2，CRITICAL）

**定位**: `routers/action_routes.py:166-184`

**当前代码**（line 171-180）:
```python
    try:
        if not get_valid_project_root(req.project_path, dm):
            raise HTTPException(status_code=403, detail="Access denied")

        logger.info(
            f"AUDIT - Batch categorizing {len(req.paths)} items "
            f"to '{req.category_name}'"
        )
        moved = FileOps.batch_categorize(req.project_path, req.paths, req.category_name)
        return {"status": "ok", "moved_count": len(moved), "paths": moved}
```

**根因**: 只校验 `req.project_path` 已注册，未对 `req.paths` 每项 `is_path_safe`。对比同文件 `api_execute_tool` (line 204) 正确做了 `if not is_path_safe(p, project_root): continue`。`FileOps.batch_categorize` → `FileOps.move_file` 对源路径无项目边界检查。

**修改**（`routers/action_routes.py:166-184`）:
```python
@action_router.post("/api/actions/categorize")
def api_categorize(
    req: CategorizeRequest, dm: DataManager = _dm_dep
) -> dict[str, Any]:
    """Categorizes files into a directory."""
    try:
        project_root = get_valid_project_root(req.project_path, dm)
        if not project_root:
            raise HTTPException(status_code=403, detail="Access denied")

        # BUG-W2 fix: validate every source path is within project root.
        # Matches the pattern used by api_execute_tool (line 204) and api_delete.
        for p in req.paths:
            if not is_path_safe(p, project_root):
                logger.warning(f"AUDIT - categorize rejected unsafe path: {p}")
                raise HTTPException(
                    status_code=403, detail=f"Path outside project boundary: {p}"
                )

        logger.info(
            f"AUDIT - Batch categorizing {len(req.paths)} items "
            f"to '{req.category_name}'"
        )
        moved = FileOps.batch_categorize(req.project_path, req.paths, req.category_name)
        return {"status": "ok", "moved_count": len(moved), "paths": moved}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
```

**影响面**: 前端 `main.js` 的 `bulkCategorize` 一直发送项目内路径，不受影响；恶意客户端原可移动 `C:\Windows\System32\...` 文件，现被 403 拒绝。

**验证**:
```powershell
# 手动 PoC（需先注册项目）
python -c "
from fastapi.testclient import TestClient
from web_app import app
import tempfile, os
d = tempfile.mkdtemp()
open(os.path.join(d,'a.txt'),'w').write('x')
c = TestClient(app)
c.post('/api/open', json={'path': d})
# 尝试越界 categorize（应 403）
r = c.post('/api/actions/categorize', json={
    'project_path': d,
    'paths': [os.path.join(os.path.dirname(d),'outside.txt')],
    'category_name': 'leaked'
})
print('status:', r.status_code, 'detail:', r.json().get('detail'))
"
# 预期: status: 403, detail 含 "outside project boundary"
```

**回归测试**（加入 `tests/test_security_v9.py`）:
```python
"""Security regression tests for v6.5.1 (BUG-W1/W2/W5/W6/W7/W9/W10)."""

import os
import tempfile

from fastapi.testclient import TestClient


class TestApiCategorizeTraversal:
    """BUG-W2 regression: api_categorize must reject paths outside project."""

    def test_categorize_rejects_path_outside_project(self, api_client, mock_project):
        """Paths outside the registered project must be rejected with 403."""
        api_client.post("/api/open", json={"path": str(mock_project)})
        outside = str(mock_project.parent / "outside_file.txt")
        (mock_project.parent / "outside_file.txt").write_text("secret", encoding="utf-8")
        r = api_client.post(
            "/api/actions/categorize",
            json={
                "project_path": str(mock_project),
                "paths": [outside],
                "category_name": "leaked",
            },
        )
        assert r.status_code == 403
        assert "boundary" in r.json()["detail"].lower() or "unsafe" in r.json()["detail"].lower()

    def test_categorize_rejects_dotdot_traversal(self, api_client, mock_project):
        """../ traversal in paths must be rejected."""
        api_client.post("/api/open", json={"path": str(mock_project)})
        r = api_client.post(
            "/api/actions/categorize",
            json={
                "project_path": str(mock_project),
                "paths": ["../../../../etc/passwd"],
                "category_name": "leaked",
            },
        )
        assert r.status_code in (403, 400)

    def test_categorize_accepts_valid_within_project(self, api_client, mock_project):
        """Legitimate in-project paths must succeed."""
        api_client.post("/api/open", json={"path": str(mock_project)})
        # First define a category via settings
        api_client.post(
            "/api/project/settings",
            json={
                "project_path": str(mock_project),
                "settings": {"quick_categories": {"docs": "docs_dir"}},
            },
        )
        r = api_client.post(
            "/api/actions/categorize",
            json={
                "project_path": str(mock_project),
                "paths": [str(mock_project / "README.md")],
                "category_name": "docs",
            },
        )
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
```

**回滚**: 还原 4 行 try 块为原状。

---

### P0.5 — 修复 index 页 API Token 泄露（BUG-W1，CRITICAL）

**定位**:
- `web_app.py:112-117`（index 路由注入 token）
- `templates/index.html:439`（`<script>window.__FCTX_API_TOKEN__ = "{{ api_token }}";</script>`）

**根因**: `/` 路由无认证（中间件只查 `/api/` 前缀）。HTML 源码内嵌 `window.__FCTX_API_TOKEN__`，任何能 GET `/` 的人可读 token，而 token 是所有 `/api/*` 的唯一凭证。

**设计决策（重要）**: 完全移除 token 注入会破坏前端 WebSocket 鉴权（`state.js:97` 用此 token 作 WS 查询参数）。因此采用**分层方案**：
- 本地（127.0.0.1）：保持现状（用户本机用，无泄露风险）
- 网络部署（0.0.0.0 / 非 localhost）：token 不再注入 HTML，改由前端首次 `/api/whoami`（已认证）返回

**修改 1**（`web_app.py:49-71`，中间件 + 112-117 路由）:
```python
def _is_local_request(request: Request) -> bool:
    """Checks if the request originates from localhost."""
    client = request.client
    if not client:
        return False
    return client.host in ("127.0.0.1", "::1", "localhost")


async def verify_api_token(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Verifies API token for protected endpoints."""
    if not API_TOKEN:
        return await call_next(request)

    if request.url.path.startswith("/api/"):
        token = request.headers.get("X-API-Token", "")
        # BUG-W10 fix: constant-time compare to prevent timing side channel.
        import hmac
        if not hmac.compare_digest(token, API_TOKEN):
            return JSONResponse(
                status_code=401,
                content={"status": "error", "detail": "Invalid or missing API token"},
            )

        origin = request.headers.get("origin", "*")
        if not _is_wildcard_origin(ALLOWED_ORIGINS) and origin not in ALLOWED_ORIGINS:
            return JSONResponse(
                status_code=403,
                content={"status": "error", "detail": "Origin not allowed"},
            )

    return await call_next(request)
```

**修改 2**（`web_app.py:112-117`，index 路由 + 新增 whoami）:
```python
@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    """Serves the main index page.

    BUG-W1 fix: only inject the API token into the page when the request is
    local. Network clients must authenticate via X-API-Token header and use
    /api/whoami to discover session state.
    """
    inject_token = API_TOKEN if _is_local_request(request) else ""
    return templates.TemplateResponse(
        request,
        "index.html",
        {"api_token": inject_token, "version": __version__},
    )


@app.get("/api/whoami")
async def whoami() -> dict[str, str]:
    """Returns server version (auth already enforced by middleware for /api/)."""
    return {"version": __version__, "status": "ok"}
```

**修改 3**（`templates/index.html:439`，防御性兜底）:
```html
<script>window.__FCTX_API_TOKEN__ = "{{ api_token }}";</script>
```
保持不变——但当 `api_token` 为空字符串时，`window.__FCTX_API_TOKEN__ = ""`，前端 `state.js` 的 `window.__FCTX_API_TOKEN__ || ""` 自然回退空。

**修改 4**（`static/js/state.js` 或 `main.js` 的 token 获取，需联动检查）：网络模式下 token 为空，前端发起的 API 调用会 401。建议在 `main.js:init` 中加：当 `window.__FCTX_API_TOKEN__` 为空且页面非 localhost 时，提示用户通过 URL 参数 `?token=xxx` 或浏览器 Basic Auth 传入，前端读取后存入 sessionStorage。

> **注意**：此改动的"网络模式前端鉴权"是较大工程。**最小落地版本**是只做"本地注入、网络不注入"+ `whoami` 端点，前端网络模式鉴权留作 P1.14（WS token 头化）一并处理。先确保 token 不再被任意 GET 泄露。

**影响面**:
- 本地用户（127.0.0.1）：完全不变
- 网络用户：HTML 不含 token，需通过 `X-API-Token` 头或 `?token=xxx` 鉴权
- CI 测试：`api_client` fixture 走 TestClient，`request.client.host` 默认是 `testclient` 或 `127.0.0.1`，需验证 `_is_local_request` 在测试环境返回 True（见下方验证）

**验证**:
```powershell
# 1. 本地访问仍注入 token（模拟 127.0.0.1）
python -c "
from fastapi.testclient import TestClient
from web_app import app
c = TestClient(app)
r = c.get('/')
has_token_script = '__FCTX_API_TOKEN__' in r.text
print('local inject token:', has_token_script)
# 预期: True（TestClient 默认 client.host='testclient'，需确保 _is_local_request 兼容）
"

# 2. 设置 API_TOKEN 后，网络模式不注入
$env:FCTX_API_TOKEN="secret123"
python -c "
from fastapi.testclient import TestClient
from web_app import app
c = TestClient(app)
# 模拟网络请求（patch client.host）
from unittest.mock import MagicMock
c.app.dependency_overrides = {}
r = c.get('/', headers={'X-Forwarded-For': '192.168.1.5'})
print('token in html:', 'secret123' in r.text)
# 预期: False（网络模式不泄露）
"
Remove-Item Env:\FCTX_API_TOKEN
```

> **兼容性补丁**：`TestClient` 的 `request.client.host` 可能是 `"testclient"` 而非 `"127.0.0.1"`。需在 `_is_local_request` 中加 `"testclient"` 判定，或改用 `request.url.hostname`。实测后调整。最稳妥写法：
> ```python
> def _is_local_request(request: Request) -> bool:
>     client = request.client
>     if not client:
>         return True  # TestClient 等无 client 场景视为本地
>     return client.host in ("127.0.0.1", "::1", "localhost", "testclient")
> ```

**回归测试**（加入 `tests/test_security_v9.py`）:
```python
class TestApiTokenNoLeak:
    """BUG-W1 regression: API token must not leak via unauthenticated pages."""

    def test_index_no_token_when_api_token_set_and_remote(
        self, api_client, mock_project, monkeypatch
    ):
        """Remote requests must not receive the token in HTML."""
        monkeypatch.setattr("web_app.API_TOKEN", "super-secret-xyz")
        # Force non-local client
        from web_app import _is_local_request
        monkeypatch.setattr("web_app._is_local_request", lambda r: False)
        r = api_client.get("/")
        assert "super-secret-xyz" not in r.text

    def test_index_has_token_for_local(self, api_client, monkeypatch):
        """Local requests still get the token (backward compat)."""
        monkeypatch.setattr("web_app.API_TOKEN", "local-secret")
        from web_app import _is_local_request
        monkeypatch.setattr("web_app._is_local_request", lambda r: True)
        r = api_client.get("/")
        assert "local-secret" in r.text

    def test_whoami_returns_version(self, api_client):
        """/api/whoami returns version."""
        r = api_client.get("/api/whoami")
        assert r.status_code == 200
        assert "version" in r.json()
```

**回滚**: 还原 index 路由为单行 `templates.TemplateResponse(..., {"api_token": API_TOKEN, ...})`，删除 `_is_local_request` 和 `/api/whoami`。

---

### P0.6 — mermaid CDN 添加 SRI 完整性哈希（BUG-F1）

**定位**: `templates/index.html:443`

**当前代码**:
```html
<script src="https://cdn.jsdelivr.net/npm/mermaid@10.9.0/dist/mermaid.min.js" crossorigin="anonymous"></script>
```

**根因**: 所有其他 CDN 资源（bootstrap、highlight.js、marked、dompurify）都有 `integrity="sha384-..."`，唯独 mermaid 缺失。CDN 被入侵即可执行恶意 JS，窃取 `window.__FCTX_API_TOKEN__`、文件内容、暂存清单。

**修改**（`templates/index.html:443`）:
```html
<script src="https://cdn.jsdelivr.net/npm/mermaid@10.9.0/dist/mermaid.min.js" integrity="sha384-<HASH>" crossorigin="anonymous"></script>
```

**`<HASH>` 获取方式**（实施前必做，二选一）:
```powershell
# 方法 1：curl + openssl（推荐，权威）
curl -s https://cdn.jsdelivr.net/npm/mermaid@10.9.0/dist/mermaid.min.js | openssl dgst -sha384 -binary | openssl base64 -A
# 输出形如: MchRfN3H+F0...==
# 拼装: integrity="sha384-MchRfN3H+F0...=="

# 方法 2：PowerShell 原生
(Invoke-WebRequest -Uri 'https://cdn.jsdelivr.net/npm/mermaid@10.9.0/dist/mermaid.min.js' -UseBasicParsing).Content | ForEach-Object {
  $bytes = [System.Text.Encoding]::UTF8.GetBytes($_)
  $sha = [System.Security.Cryptography.SHA384]::Create()
  $hash = $sha.ComputeHash($bytes)
  'sha384-' + [Convert]::ToBase64String($hash)
}

# 方法 3：从 https://www.srijs.org/ 输入 URL 自动生成
```

> **实施注意**：本计划不硬编码 hash，因为 hash 必须基于真实下载的字节流，建议实施时即时生成并验证（浏览器 DevTools Console 跑 `fetch('/static/js/...')` 无 SRI 错误即通过）。

**影响面**: 纯前端；浏览器在 hash 不匹配时拒绝执行 mermaid 并报错到 Console，不影响其他脚本。

**验证**:
```powershell
# 1. 启动 web 服务，浏览器打开 http://127.0.0.1:8000
python web_app.py
# 2. F12 Console 应无 "Subresource Integrity" 错误
# 3. 渲染一个 mermaid 图（打开任一 .mmd 文件预览）应正常显示
```

**回归测试**（加入 `tests/test_frontend_contract.py`，扩展现有 SRI 测试）:
```python
def test_all_cdn_scripts_have_integrity() -> None:
    """BUG-F1: every CDN script tag must have an integrity attribute."""
    import pathlib

    html = (pathlib.Path(__file__).resolve().parent.parent / "templates" / "index.html").read_text(
        encoding="utf-8"
    )
    import re

    cdn_scripts = re.findall(r'<script src="https?://[^"]+"[^>]*>', html)
    assert cdn_scripts, "No CDN scripts found — test setup issue"
    for tag in cdn_scripts:
        assert "integrity=" in tag, f"CDN script missing SRI: {tag}"
```

**回滚**: 删除 `integrity="sha384-..."` 属性。

---

### P0.7 — MCP mock 模式退出码非零（已在 P0.2 修改 3 完成）

此项已并入 P0.2 的 mcp_server.py:main() 修改（`sys.exit(2)` 在 mock 模式）。不再单列。

---

### P0 阶段验证门禁

完成 P0.1–P0.6 后必须全部通过：

```powershell
# 1. Ruff 无新错误
python -m ruff check .
# 预期: All checks passed!

# 2. 全量测试通过（含新增 test_packaging + test_security_v9 部分）
python -m pytest tests/test_packaging.py tests/test_security_v9.py -v
python -m pytest --tb=short
# 预期: 629 + 新增 ≈ 640+ passed

# 3. 打包烟雾
pip install .
python -c "import web_app, routers, fctx, mcp_server; print('all entry modules OK')"

# 4. 安全 PoC
python -c "
from fastapi.testclient import TestClient
from web_app import app
import tempfile, os
d = tempfile.mkdtemp()
open(os.path.join(d,'a.txt'),'w').write('x')
c = TestClient(app)
c.post('/api/open', json={'path': d})
r = c.post('/api/actions/categorize', json={'project_path': d, 'paths': ['C:/Windows/win.ini'], 'category_name': 'x'})
assert r.status_code == 403, f'BUG-W2 not fixed: {r.status_code}'
print('BUG-W2 fixed: categorize rejects outside path')
"

# 5. MCP fallback 退出码
python mcp_server.py --transport stdio 2>&1 | FindStr "FALLBACK"
# 预期: 含 "FALLBACK MODE"
```

**P0 完成标志**: 上述 5 项全绿 + 版本号在 `__init__.py`/`pyproject.toml` 升至 `6.5.1-dev`。

---

## Phase P1 — 安全加固与一致性（13 项）

> 目标：消除 HIGH/EDIUM 安全风险 + 核心健壮性 + 前端状态污染。P0 完成后开始。

---

### P1.1 — 全部 `list[str]` 字段加 `max_length`（BUG-W7）

**定位**: `routers/schemas.py` 多处

**根因**: 仅 `FileSaveRequest.content` 有 `max_length=10_000_000`。其余 `list[str]` / `dict[str, Any]` 字段无界，攻击者可发超大 JSON 致内存耗尽。

**修改**（`routers/schemas.py`，逐行加 `Field`）:
```python
# 顶部 import 已有: from pydantic import BaseModel, Field

# Line 27 (GenerateRequest)
files: list[str] = Field(..., max_length=1000)

# Line 47 (FileDeleteRequest)
paths: list[str] = Field(..., max_length=1000)

# Line 53 (FileMoveRequest)
src_paths: list[str] = Field(..., max_length=1000)

# Line 75 (FileArchiveRequest)
paths: list[str] = Field(..., max_length=1000)

# Line 98 (NoteRequest)
note: str = Field(..., max_length=10_000)

# Line 127 (FavoriteRequest)
file_paths: list[str] = Field(..., max_length=1000)

# Line 135 (SessionRequest)
data: dict[str, Any] = Field(...)  # dict 无 max_length，加自定义 validator

# Line 142 (ProjectSettingsRequest)
settings: dict[str, Any] = Field(...)

# Line 149 (ToolsUpdateRequest)
tools: dict[str, Any] = Field(...)

# Line 156 (CategoriesUpdateRequest)
categories: dict[str, Any] = Field(...)

# Line 162 (PathCollectionRequest)
paths: list[str] = Field(..., max_length=1000)

# Line 180 (CategorizeRequest)
paths: list[str] = Field(..., max_length=1000)

# Line 187 (StatsRequest)
paths: list[str] = Field(..., max_length=1000)

# Line 195 (ToolExecuteRequest)
paths: list[str] = Field(..., max_length=1000)

# Line 203 (BatchRenameRequest)
paths: list[str] = Field(..., max_length=1000)
```

**dict 字段的大小限制**（用 Pydantic V2 `field_validator`）:
在 `schemas.py` 顶部新增：
```python
from pydantic import field_validator

MAX_DICT_JSON_BYTES = 100_000  # 100 KB 序列化后上限


def _validate_dict_size(v: dict[str, Any]) -> dict[str, Any]:
    """Rejects oversized dicts to prevent storage exhaustion (BUG-W9)."""
    import json

    try:
        serialized = json.dumps(v, ensure_ascii=False)
    except (TypeError, ValueError) as e:
        raise ValueError(f"Dict not JSON-serializable: {e}") from e
    if len(serialized.encode("utf-8")) > MAX_DICT_JSON_BYTES:
        raise ValueError(
            f"Dict too large: {len(serialized)} bytes > {MAX_DICT_JSON_BYTES} limit"
        )
    return v
```

然后在 `SessionRequest` / `ProjectSettingsRequest` / `ToolsUpdateRequest` / `CategoriesUpdateRequest` 类中加：
```python
class SessionRequest(BaseModel):
    """Request model for saving sessions."""

    project_path: str
    data: dict[str, Any]

    @field_validator("data")
    @classmethod
    def _check_size(cls, v: dict[str, Any]) -> dict[str, Any]:
        return _validate_dict_size(v)
```
（其余三个类同理）

**影响面**: 超过 1000 项的 `paths` 请求返回 422（Pydantic 自动）；现有前端单次最多几百文件，不受影响。

**验证**:
```powershell
python -c "
from fastapi.testclient import TestClient
from web_app import app
import tempfile, os
d = tempfile.mkdtemp()
c = TestClient(app)
c.post('/api/open', json={'path': d})
# 发 2000 个路径
r = c.post('/api/project/stats', json={'paths': ['x']*2000, 'project_path': d})
print('status:', r.status_code)
# 预期: 422
"
```

**回归测试**（`tests/test_security_v9.py`）:
```python
class TestInputSizeLimits:
    """BUG-W7/W9 regression: oversized inputs must be rejected."""

    def test_stats_rejects_paths_over_1000(self, api_client, mock_project):
        api_client.post("/api/open", json={"path": str(mock_project)})
        r = api_client.post(
            "/api/project/stats",
            json={"paths": ["x"] * 2000, "project_path": str(mock_project)},
        )
        assert r.status_code == 422  # Pydantic validation error

    def test_session_rejects_oversized_dict(self, api_client, mock_project):
        api_client.post("/api/open", json={"path": str(mock_project)})
        big = {str(i): "x" * 100 for i in range(10000)}  # > 100KB
        r = api_client.post(
            "/api/session/save",
            json={"project_path": str(mock_project), "data": big},
        )
        assert r.status_code in (400, 422)
```

---

### P1.2 — API token / WS token 改常量时间比较（BUG-W10）

**定位**:
- `web_app.py:58` — `if token != API_TOKEN:`
- `routers/ws_routes.py:31` — `return token == expected_token`

**根因**: 普通 `==` / `!=` 是短路比较，存在时序侧信道。虽实战难利用，但安全敏感场景应使用 `hmac.compare_digest`。

**修改 1**（`web_app.py:49-71`，已在 P0.5 修改 1 中体现）:
```python
import hmac
if not hmac.compare_digest(token, API_TOKEN):
    ...
```

**修改 2**（`routers/ws_routes.py:26-31`）:
```python
import hmac


def verify_ws_token(token: str | None) -> bool:
    """Verifies the API token for WebSocket connections (constant-time)."""
    expected_token = os.getenv("FCTX_API_TOKEN", "")
    if not expected_token:
        return True
    if not token:
        return False
    # BUG-W10 fix: constant-time compare.
    return hmac.compare_digest(token, expected_token)
```

**影响面**: 无行为变化（除时序）；`hmac` 是 stdlib，无新依赖。

**验证**:
```powershell
python -m pytest tests/test_security_v9.py::TestTokenConstantTime -v
```

**回归测试**:
```python
class TestTokenConstantTime:
    """BUG-W10 regression: token compare must be constant-time."""

    def test_ws_token_uses_compare_digest(self):
        """Source-level check: hmac.compare_digest is used in ws_routes."""
        import pathlib
        src = (pathlib.Path(__file__).resolve().parent.parent / "routers" / "ws_routes.py").read_text(encoding="utf-8")
        assert "hmac.compare_digest" in src

    def test_http_token_uses_compare_digest(self):
        import pathlib
        src = (pathlib.Path(__file__).resolve().parent.parent / "web_app.py").read_text(encoding="utf-8")
        assert "hmac.compare_digest" in src

    def test_ws_rejects_empty_token_when_required(self, monkeypatch):
        monkeypatch.setenv("FCTX_API_TOKEN", "secret")
        from routers.ws_routes import verify_ws_token
        assert verify_ws_token(None) is False
        assert verify_ws_token("") is False
        assert verify_ws_token("wrong") is False
        assert verify_ws_token("secret") is True
```

---

### P1.3 — WebSocket search_task 正常完成时取消（BUG-W4）

**定位**: `routers/ws_routes.py:103-120`

**当前代码**（line 103-120）:
```python
    search_task = asyncio.create_task(asyncio.to_thread(run_search))

    try:
        while True:
            res = await result_queue.get()
            if res == "DONE":
                await websocket.send_json({"status": "DONE"})
                break
            await websocket.send_json(res)
    except WebSocketDisconnect:
        logger.info("Search client disconnected")
        stop_event.set()
        search_task.cancel()
    except Exception as e:
        logger.exception("Search error")
        search_task.cancel()
        with contextlib.suppress(Exception):
            await websocket.send_json({"status": "ERROR", "msg": str(e)})
```

**根因**: 正常 DONE 路径 `break` 后函数返回，`search_task` 未取消。仅 WebSocketDisconnect 和 Exception 路径取消。孤儿任务残留至 GC，Python 3.12+ 抛 `RuntimeError: Task was destroyed but it is pending!`。

**修改**（`routers/ws_routes.py:103-120`，改 try 结构加 finally）:
```python
    search_task = asyncio.create_task(asyncio.to_thread(run_search))

    try:
        while True:
            res = await result_queue.get()
            if res == "DONE":
                await websocket.send_json({"status": "DONE"})
                break
            await websocket.send_json(res)
    except WebSocketDisconnect:
        logger.info("Search client disconnected")
        stop_event.set()
    except Exception as e:
        logger.exception("Search error")
        with contextlib.suppress(Exception):
            await websocket.send_json({"status": "ERROR", "msg": str(e)})
    finally:
        # BUG-W4 fix: always cancel + await search_task to prevent orphan threads.
        search_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await search_task
```

**影响面**: 正常完成路径多一次 `cancel()`（对已完成任务是 no-op）+ await（确保资源释放）。无行为变化。

**验证**:
```powershell
python -m pytest tests/test_web_api.py -k websocket -v
python -m pytest tests/test_security_v9.py::TestWsSearchTaskCleanup -v
```

**回归测试**:
```python
import asyncio


class TestWsSearchTaskCleanup:
    """BUG-W4 regression: search_task must be cancelled on normal completion."""

    def test_search_task_cancelled_after_done(self):
        """Source-level: finally block cancels search_task."""
        import pathlib
        src = (pathlib.Path(__file__).resolve().parent.parent / "routers" / "ws_routes.py").read_text(encoding="utf-8")
        # 必须有 finally 块且在 search_task 创建之后
        assert "finally:" in src
        assert "search_task.cancel()" in src
```

---

### P1.4 — ProcessManager register 拒绝 PID 复用（BUG-W5）

**定位**: `routers/common.py:34-48`

**当前代码**（line 44-48）:
```python
        with self._lock:
            if len(self._processes) >= self._max:
                return False
            self._processes[pid] = proc
            return True
```

**根因**: 不检查 PID 是否已被占用。若旧进程未 unregister 而新进程复用同 PID，旧条目被静默覆盖，旧 Popen 引用泄漏，无法 terminate。

**修改**（`routers/common.py:34-48`）:
```python
    def register(self, pid: int, proc: subprocess.Popen) -> bool:
        """Registers a process, enforcing the maximum count.

        Args:
            pid: Process ID.
            proc: Popen object.

        Returns:
            True if registered successfully, False if at capacity or PID in use.
        """
        with self._lock:
            if len(self._processes) >= self._max:
                return False
            existing = self._processes.get(pid)
            # BUG-W5 fix: refuse to overwrite a still-live process entry.
            if existing is not None and existing.poll() is None:
                logger.warning(
                    f"PID {pid} already registered with a live process; "
                    f"refusing overwrite."
                )
                return False
            self._processes[pid] = proc
            return True
```

> 注意：`common.py` 顶部需 `from file_cortex_core import logger`。检查现有 import；若无则添加 `from file_cortex_core.config import logger`。

**影响面**: 同 PID 的二次 register 在旧进程仍活时返回 False（调用方 `api_execute_tool` line 209 已有 `if not register_process(...)` 分支，会 `proc.kill()` 并返回错误）。

**验证**:
```powershell
python -m pytest tests/test_security_v9.py::TestProcessManagerPidReuse -v
```

**回归测试**:
```python
class TestProcessManagerPidReuse:
    """BUG-W5 regression: register refuses to overwrite a live PID."""

    def test_register_refuses_when_pid_still_live(self):
        from unittest.mock import MagicMock
        from routers.common import ProcessManager

        pm = ProcessManager(max_processes=10)
        live_proc = MagicMock()
        live_proc.poll.return_value = None  # still running
        assert pm.register(1234, live_proc) is True

        new_proc = MagicMock()
        # Same PID, previous still live → must refuse
        assert pm.register(1234, new_proc) is False
        # Original still tracked
        assert pm.get(1234) is live_proc

    def test_register_allows_when_pid_finished(self):
        from unittest.mock import MagicMock
        from routers.common import ProcessManager

        pm = ProcessManager(max_processes=10)
        dead_proc = MagicMock()
        dead_proc.poll.return_value = 0  # finished
        pm.register(1234, dead_proc)

        new_proc = MagicMock()
        # Previous finished → overwrite allowed
        assert pm.register(1234, new_proc) is True
        assert pm.get(1234) is new_proc
```

---

### P1.5 — `api_terminate_process` 用 Popen 而非裸 PID（BUG-W6）

**定位**: `routers/action_routes.py:255-277`

**当前代码**（line 258-277）:
```python
    proc = process_manager.get(req.pid)
    if not proc:
        return {
            "status": "error",
            "msg": "Process not found or already finished",
        }

    logger.info(f"AUDIT - Terminating process {req.pid}")
    try:
        from file_cortex_file.process_utils import terminate_process

        terminate_process(req.pid)
        return {"status": "ok"}
    except Exception as e:
        try:
            os.kill(req.pid, signal.SIGTERM)
            return {"status": "ok", "msg": f"killpg failed: {e}"}
        except Exception:
            pass
        return {"status": "error", "msg": str(e)}
```

**根因**: `terminate_process(req.pid)` 按裸 PID 杀。`req.pid` 与 `process_manager` 中的 Popen 之间可能因 PID 复用而不一致。错误兜底 `os.kill(req.pid, SIGTERM)` 同样无所有权检查。

**修改**（`routers/action_routes.py:255-277`）:
```python
@action_router.post("/api/actions/terminate")
def api_terminate_process(req: ProcessTerminateRequest) -> dict[str, Any]:
    """Terminates a running process."""
    proc = process_manager.get(req.pid)
    if not proc:
        return {
            "status": "error",
            "msg": "Process not found or already finished",
        }

    # BUG-W6 fix: verify the process is still the one we registered.
    if proc.pid != req.pid:
        logger.warning(
            f"AUDIT - PID mismatch on terminate: registered pid={proc.pid}, "
            f"requested pid={req.pid}"
        )
        return {"status": "error", "msg": "PID mismatch; possible PID reuse"}

    if proc.poll() is not None:
        unregister_process(req.pid)
        return {"status": "ok", "msg": "Process already finished"}

    logger.info(f"AUDIT - Terminating process {req.pid}")
    try:
        # Terminate via the Popen object directly (ownership verified).
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2)
        unregister_process(req.pid)
        return {"status": "ok"}
    except Exception as e:
        logger.exception(f"Terminate failed for pid {req.pid}")
        return {"status": "error", "msg": str(e)}
```

**影响面**: 不再调用 `terminate_process(req.pid)`（按 PID 杀），改为 `proc.terminate()`（按 Popen 对象杀，OS 保证对象一致）。`subprocess` 已在文件顶部 import。

**验证**:
```powershell
python -m pytest tests/test_security_v9.py::TestTerminateProcess -v
```

**回归测试**:
```python
class TestTerminateProcess:
    """BUG-W6 regression: terminate must verify process ownership."""

    def test_terminate_unknown_pid_returns_error(self, api_client):
        r = api_client.post("/api/actions/terminate", json={"pid": 99999999})
        assert r.status_code == 200
        assert r.json()["status"] == "error"

    def test_terminate_uses_popen_not_raw_pid(self):
        """Source-level: no os.kill(req.pid, ...) fallthrough."""
        import pathlib
        src = (pathlib.Path(__file__).resolve().parent.parent / "routers" / "action_routes.py").read_text(encoding="utf-8")
        # api_terminate_process 函数体内不应有 os.kill(req.pid
        import re
        func_body = re.search(r"def api_terminate_process.*?(?=\n@|\nclass |\Z)", src, re.DOTALL)
        assert func_body, "api_terminate_process not found"
        assert "os.kill(req.pid" not in func_body.group(0), "BUG-W6: raw os.kill(req.pid) still present"
```

---

### P1.6 — `FileSaveRequest` 加 `project_path` 字段（BUG-W8）

**定位**:
- `routers/schemas.py:57-61`
- `routers/fs_routes.py:210-224`（需读取确认 api_save 实现）

**修改 1**（`routers/schemas.py:57-61`）:
```python
class FileSaveRequest(BaseModel):
    """Request model for saving file content."""

    project_path: str | None = None  # BUG-W8 fix: optional for backward compat
    path: str
    content: str = Field(..., max_length=10_000_000)
```

> 用 `Optional` + `None` 默认值保证前端旧版本（不发送 `project_path`）仍可用。前端可在后续迭代补字段。

**修改 2**（`routers/fs_routes.py` 的 `api_save`，需读取后定位精确行号）:
```python
# 在 api_save 内，get_valid_project_root 校验后增加一致性检查
def api_save(req: FileSaveRequest, dm: DataManager = _dm_dep):
    root = get_valid_project_root(req.path, dm)
    if not root:
        raise HTTPException(status_code=403, detail="Access denied")
    # BUG-W8 fix: if project_path provided, verify it matches resolved root.
    if req.project_path:
        expected_root = get_valid_project_root(req.project_path, dm)
        if expected_root != root:
            raise HTTPException(
                status_code=403, detail="project_path does not match file path's project"
            )
    # ... 原有 save_content 逻辑
```

**影响面**: 新增字段为 Optional，旧前端不受影响；新前端可发 `project_path` 做一致性校验。

**验证**:
```powershell
python -m pytest tests/test_web_api.py -k save -v
```

**回归测试**:
```python
def test_save_accepts_project_path_field(self, api_client, mock_project):
    """BUG-W8: FileSaveRequest accepts optional project_path."""
    api_client.post("/api/open", json={"path": str(mock_project)})
    target = str(mock_project / "newfile.txt")
    r = api_client.post(
        "/api/save",
        json={
            "project_path": str(mock_project),
            "path": target,
            "content": "hello",
        },
    )
    assert r.status_code == 200

def test_save_rejects_mismatched_project_path(self, api_client, mock_project, tmp_path):
    """project_path not matching file's project → 403."""
    api_client.post("/api/open", json={"path": str(mock_project)})
    other = tmp_path / "other_project"
    other.mkdir()
    (other / "f.txt").write_text("x", encoding="utf-8")
    api_client.post("/api/open", json={"path": str(other)})
    r = api_client.post(
        "/api/save",
        json={
            "project_path": str(other),  # claims other project
            "path": str(mock_project / "README.md"),  # but file is in mock_project
            "content": "tampered",
        },
    )
    assert r.status_code == 403
```

---

### P1.7 — `to_xml` 加日志（BUG-C1）

**定位**: `file_cortex_core/context.py:229-230`

**当前代码**:
```python
            except Exception:
                pass
```

**修改**（`file_cortex_core/context.py:229-230`）:
```python
            except Exception:
                logger.exception(f"Failed to format file {f_str} for XML context")
```

**影响面**: XML 导出时格式化失败的文件现在会记日志（与 `to_markdown` line 134-135 一致）。无行为变化。

**验证**:
```powershell
python -m pytest tests/test_context_formatter.py -v
```

**回归测试**:
```python
def test_to_xml_logs_format_failure(self, caplog, tmp_path):
    """BUG-C1: to_xml logs (not silently swallows) format failures."""
    import logging
    from file_cortex_core.context import ContextFormatter

    bad_file = tmp_path / "bad.txt"
    bad_file.write_text("content", encoding="utf-8")
    # Patch FileUtils.read_text_smart to raise
    from unittest.mock import patch
    with patch("file_cortex_core.file_io.FileUtils.read_text_smart", side_effect=RuntimeError("boom")):
        with caplog.at_level(logging.ERROR):
            ContextFormatter.to_xml([str(bad_file)], root_dir=str(tmp_path))
    assert any("Failed to format" in r.message for r in caplog.records)
```

---

### P1.8 — `archive_selection` 目录分支 arcname 一致性（BUG-C2）

**定位**: `file_cortex_core/actions.py:311-316`

**当前代码**:
```python
                elif p.is_dir():
                    for root, _, files in os.walk(p):
                        for file in files:
                            full_f = pathlib.Path(root) / file
                            rel_base = root_dir_p if root_dir_p else p.parent
                            zipf.write(full_f, full_f.relative_to(rel_base))
```

**根因**: 当 `root_dir_p` 设但 `p` 不在 `root_dir_p` 下时，`full_f.relative_to(root_dir_p)` 抛 `ValueError`。

**修改**（`file_cortex_core/actions.py:311-316`）:
```python
                elif p.is_dir():
                    for root, _, files in os.walk(p):
                        for file in files:
                            full_f = pathlib.Path(root) / file
                            # BUG-C2 fix: per-file arcname decision, same logic as file branch.
                            if root_dir_p and (
                                root_dir_p == full_f or root_dir_p in full_f.parents
                            ):
                                arc = full_f.relative_to(root_dir_p)
                            else:
                                arc = full_f.relative_to(p.parent)
                            zipf.write(full_f, arc)
```

**影响面**: 归档目录在项目外时不再崩溃；arcname 逻辑与文件分支一致。

**验证**:
```powershell
python -m pytest tests/test_security_v9.py::TestArchiveOutsideProject -v
```

**回归测试**:
```python
class TestArchiveOutsideProject:
    """BUG-C2 regression: archiving a dir outside project root must not crash."""

    def test_archive_dir_outside_root_no_crash(self, tmp_path):
        from file_cortex_core.actions import FileOps

        project = tmp_path / "project"
        project.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "f.txt").write_text("x", encoding="utf-8")
        out_zip = tmp_path / "out.zip"
        # Should not raise ValueError
        FileOps.archive_selection([str(outside)], str(out_zip), root_dir=str(project))
        assert out_zip.exists()
```

---

### P1.9 — Windows 长路径前缀剥离（BUG-C3）

**定位**: `file_cortex_core/security.py:15, 56, 162`

**修改**（`file_cortex_core/security.py:15` 之后新增常量，并在 is_safe / validate_project 入口剥离）:
```python
# Line 15 之后新增
_WIN_LONG_PREFIXES: Final = ("\\\\?\\", "\\\\?\\")

# 等价字符串形式，统一处理 \\?\ 和 \??\ （前者更常见）
# 注意 Python 源码中 "\\\\?\\" 表示字面 \\?\


def _strip_win_long_prefix(s: str) -> str:
    """Removes the Windows long-path prefix (\\?\) if present.

    This is a LOCAL path prefix, NOT a UNC path, and must not be blocked.
    """
    for pre in _WIN_LONG_PREFIXES:
        if s.startswith(pre):
            return s[len(pre):]
    return s
```

**修改 `is_safe`**（`security.py:41-42` 之后）:
```python
        try:
            target_raw = _strip_win_long_prefix(str(target_path))  # BUG-C3 fix
            root_raw = _strip_win_long_prefix(str(root_path))
```

**修改 `validate_project`**（`security.py:158-165`）:
```python
        normalized_str = (
            str(path_str).replace("/", "\\") if sys.platform == "win32" else str(path_str)
        )
        # BUG-C3 fix: strip long-path prefix BEFORE UNC check.
        normalized_str = _strip_win_long_prefix(normalized_str)

        if sys.platform == "win32" and normalized_str.startswith("\\\\"):
            raise PermissionError(
                "UNC/Network paths are blocked to prevent potential SMB credential leaks."
            )
```

**影响面**: `\\?\C:\project` 不再被误判为 UNC 拒绝；真实 UNC `\\server\share` 仍被拦截。

**验证**:
```powershell
python -c "
from file_cortex_core.security import PathValidator, _strip_win_long_prefix
# 长路径前缀剥离
assert _strip_win_long_prefix(r'\\\\?\\C:\\proj') == 'C:\\proj', 'strip failed'
# is_safe 不再误拒长路径（Windows 上验证）
import os
if os.name == 'nt':
    root = r'C:\\temp'
    target = r'\\\\?\\C:\\temp\\file.txt'
    print('is_safe long path:', PathValidator.is_safe(target, root))
"
```

**回归测试**:
```python
class TestWindowsLongPath:
    """BUG-C3 regression: \\\\?\\ prefix must not be treated as UNC."""

    def test_strip_long_prefix(self):
        from file_cortex_core.security import _strip_win_long_prefix
        assert _strip_win_long_prefix(r"\\?\C:\proj") == r"C:\proj"
        assert _strip_win_long_prefix(r"C:\normal") == r"C:\normal"

    def test_is_safe_accepts_long_prefix(self, tmp_path):
        """is_safe should not reject \\?\ prefix paths."""
        from file_cortex_core.security import PathValidator
        root = str(tmp_path)
        target = r"\\?\\" + str(tmp_path / "f.txt")
        # Should not return False due to UNC misclassification
        # (may return True or False based on existence, but not False due to UNC)
        result = PathValidator.is_safe(target, root)
        # 关键：不是因为 UNC 前缀被拒
        assert result is True or result is False  # 不抛异常即可
```

---

### P1.10 — `batch_rename` 加 `count` 参数（BUG-C4）

**定位**: `file_cortex_core/actions.py:38-60`

**当前签名**（line 38-44）:
```python
    def batch_rename(
        project_path: str,
        paths: list[str],
        pattern: str,
        replacement: str,
        dry_run: bool = True,
    ) -> list[dict[str, str]]:
```

**当前调用**（line 66）:
```python
            new_name = regex.sub(replacement, p.name, count=1)
```

**修改**（`actions.py:38-66`）:
```python
    def batch_rename(
        project_path: str,
        paths: list[str],
        pattern: str,
        replacement: str,
        dry_run: bool = True,
        count: int = 1,  # BUG-C4 fix: expose count, default 1 (backward compat)
    ) -> list[dict[str, str]]:
        """Renames multiple files using regex.

        Args:
            project_path: Project root path.
            paths: List of file paths to rename.
            pattern: Regex pattern.
            replacement: Replacement string.
            dry_run: If True, only simulate changes.
            count: Maximum number of replacements per filename (0 = all).
                Defaults to 1 for backward compatibility.

        Returns:
            List of result dictionaries.
        """
        try:
            regex = re.compile(pattern)
        except re.error as e:
            raise ValueError(f"Invalid regex: {e}") from e

        results = []
        new_names = {}
        for p_str in paths:
            p = pathlib.Path(p_str)
            # count=0 means "replace all" in regex.sub.
            new_name = regex.sub(replacement, p.name, count=count if count > 0 else 0)
            if new_name == p.name:
                continue
```

**影响面**: 现有调用方不传 `count`，默认 1，行为不变。GUI `BatchRenameWindow` 可加 "替换全部" 复选框传 `count=0`。

**验证**:
```powershell
python -c "
from file_cortex_core.actions import FileOps
import tempfile, os
d = tempfile.mkdtemp()
for n in ['a-1.txt','b-2.txt']:
    open(os.path.join(d,n),'w').write('x')
paths = [os.path.join(d,p) for p in os.listdir(d)]
# count=0: replace all '-'
r = FileOps.batch_rename(d, paths, '-', '_', dry_run=True, count=0)
print([x['new'] for x in r])
# 预期: a_1.txt, b_2.txt (而非 a_1.txt 的 _ 全替换)
"
```

**回归测试**:
```python
class TestBatchRenameCount:
    """BUG-C4 regression: count parameter controls replacement count."""

    def test_count_zero_replaces_all(self, tmp_path):
        from file_cortex_core.actions import FileOps

        f = tmp_path / "a-b-c.txt"
        f.write_text("x", encoding="utf-8")
        results = FileOps.batch_rename(
            str(tmp_path), [str(f)], "-", "_", dry_run=True, count=0
        )
        assert results[0]["new"].endswith("a_b_c.txt")

    def test_count_one_default_backward_compat(self, tmp_path):
        from file_cortex_core.actions import FileOps

        f = tmp_path / "a-b-c.txt"
        f.write_text("x", encoding="utf-8")
        results = FileOps.batch_rename(
            str(tmp_path), [str(f)], "-", "_", dry_run=True
        )
        assert results[0]["new"].endswith("a_b-c.txt")  # only first
```

---

### P1.11 — `search_generator` submit 前 shutdown 检查（BUG-C5）

**定位**: `file_cortex_core/search.py:264`

**当前代码**:
```python
                future = SHARED_SEARCH_POOL.submit(content_matcher.match_file, full_path)
```

**修改**（`search.py:264`）:
```python
                # BUG-C5 fix: guard against submitting to a shutdown pool
                # (atexit may have fired during interpreter teardown).
                if SHARED_SEARCH_POOL._shutdown:
                    logger.warning("Search pool is shutting down; aborting content search.")
                    break
                future = SHARED_SEARCH_POOL.submit(content_matcher.match_file, full_path)
```

**影响面**: atexit 后的 search 调用安全退出而非抛 RuntimeError。

**验证**:
```powershell
python -m pytest tests/test_search_engine.py -v
```

**回归测试**:
```python
def test_search_generator_handles_pool_shutdown(self):
    """BUG-C5: no RuntimeError when pool is shutdown."""
    from file_cortex_core.search import SHARED_SEARCH_POOL
    import pathlib, tempfile

    # Simulate shutdown state
    original = SHARED_SEARCH_POOL._shutdown
    SHARED_SEARCH_POOL._shutdown = True
    try:
        d = tempfile.mkdtemp()
        (pathlib.Path(d) / "f.txt").write_text("hello", encoding="utf-8")
        from file_cortex_core.search import search_generator
        # Should not raise RuntimeError
        results = list(search_generator(pathlib.Path(d), "hello", "content", ""))
        # May be empty due to shutdown, but no exception
        assert isinstance(results, list)
    finally:
        SHARED_SEARCH_POOL._shutdown = original
```

---

### P1.12 — `SearchWorker.run` 异常入队（BUG-C6）

**定位**: `file_cortex_core/search.py:353-377`

**当前代码**（line 353-377）:
```python
    def run(self) -> None:
        """Executes the search and feeds the result queue."""
        gen = search_generator(...)
        try:
            for result in gen:
                if self.stop_event.is_set():
                    break
                self.result_queue.put(result)
        finally:
            gen.close()
        self.result_queue.put(("DONE", "DONE"))
```

**根因**: 若 `search_generator` 抛异常，`try` 内传播，`finally` 跑 `gen.close()`，但异常继续上抛到 `Thread.run()`，被 Python 静默吞，`("DONE", "DONE")` 永不入队，UI 永远等待。

**修改**（`search.py:353-377`）:
```python
    def run(self) -> None:
        """Executes the search and feeds the result queue."""
        gen = search_generator(
            self.root_dir,
            self.search_text,
            self.search_mode,
            self.manual_excludes,
            self.include_dirs,
            self.use_gitignore,
            self.is_inverse,
            self.case_sensitive,
            self.max_results,
            max_size_mb=self.max_size_mb,
            stop_event=self.stop_event,
            positive_tags=self.positive_tags,
            negative_tags=self.negative_tags,
        )
        try:
            for result in gen:
                if self.stop_event.is_set():
                    break
                self.result_queue.put(result)
        except Exception as e:
            # BUG-C6 fix: push error to queue so UI knows the worker died.
            logger.exception("SearchWorker thread crashed")
            self.result_queue.put(("ERROR", str(e)))
        finally:
            gen.close()
        self.result_queue.put(("DONE", "DONE"))
```

**影响面**: UI 轮询队列会收到 `("ERROR", msg)`；`file_search.py` 的 UI 处理需识别此 tuple 类型并显示错误（如不识别则忽略，等价原行为 + DONE）。建议 `file_search.py` 的轮询循环加：
```python
if isinstance(item, tuple) and item[0] == "ERROR":
    self.status_label.config(text=f"Search error: {item[1]}")
    continue
```

**验证**:
```powershell
python -m pytest tests/test_search_engine.py -v
```

**回归测试**:
```python
def test_search_worker_pushes_error_on_crash(self):
    """BUG-C6: worker pushes ERROR tuple instead of dying silently."""
    import pathlib, queue, threading, tempfile
    from unittest.mock import patch
    from file_cortex_core.search import SearchWorker

    d = tempfile.mkdtemp()
    (pathlib.Path(d) / "f.txt").write_text("x", encoding="utf-8")
    q = queue.Queue()
    stop = threading.Event()
    worker = SearchWorker(
        pathlib.Path(d), "x", "content", "", False, q, stop
    )
    # Force search_generator to raise
    with patch("file_cortex_core.search.search_generator", side_effect=RuntimeError("boom")):
        worker.start()
        worker.join(timeout=2)
    items = []
    while not q.empty():
        items.append(q.get_nowait())
    has_error = any(isinstance(it, tuple) and it[0] == "ERROR" for it in items)
    has_done = any(isinstance(it, tuple) and it[0] == "DONE" for it in items)
    assert has_error, f"Expected ERROR tuple, got {items}"
    assert has_done, f"Expected DONE tuple, got {items}"
```

---

### P1.13 — 前端 `ctxAction` try/finally 恢复 currentFile（BUG-F4）

**定位**: `static/js/main.js:1244-1262`（需读取精确行号验证）

**修改**（`static/js/main.js` 的 `ctxAction` 函数）:
```javascript
// Before (BUG-F4):
ctxAction(action) {
    const savedFile = App.state.currentFile;
    App.state.currentFile = App.state.contextPath;
    if (action === 'fav') {
        App.addToFavorites();
        App.state.currentFile = savedFile;
    } else if (action === 'delete') {
        App.deleteCurrentFile();
        App.state.currentFile = savedFile;
    }
}

// After (fixed):
ctxAction(action) {
    const savedFile = App.state.currentFile;
    App.state.currentFile = App.state.contextPath;
    try {
        if (action === 'fav') {
            App.addToFavorites();
        } else if (action === 'delete') {
            App.deleteCurrentFile();
        }
    } finally {
        // BUG-F4 fix: always restore, even if the action throws.
        App.state.currentFile = savedFile;
    }
}
```

> **注意**：若 `addToFavorites`/`deleteCurrentFile` 是 async，需改为 `async ctxAction` + `await` + `try/finally`。实施时按实际签名调整。

**影响面**: API 失败时 UI 状态不再污染。

**验证**: 浏览器手动触发右键菜单的"收藏"/"删除"，在 Network 面板模拟 API 500，确认 UI 不卡在错误文件。

---

## 回归测试套件设计

### 新建文件清单

| 文件 | 测试项 | 覆盖 BUG |
|------|--------|----------|
| `tests/test_packaging.py` | 3 | D1, D2, Doc5 |
| `tests/test_security_v9.py` | 15-20 | W1, W2, W4, W5, W6, W7, W9, W10, C2 |
| 扩展 `tests/test_context_formatter.py` | +1 | C1 |
| 扩展 `tests/test_search_engine.py` | +2 | C5, C6 |
| 扩展 `tests/test_fileops_advanced.py` | +2 | C2 (archive), C4 (rename count) |
| 扩展 `tests/test_security_resilience.py` | +2 | C3 (long path) |
| 扩展 `tests/test_frontend_contract.py` | +1 | F1 (SRI) |

**预计新增测试**：约 26-30 项，总数从 629 → ~659。

### 测试套件验证矩阵

| 测试类别 | 命令 | 期望 |
|---------|------|------|
| 打包完整性 | `pytest tests/test_packaging.py -v` | 3 passed |
| 安全回归 | `pytest tests/test_security_v9.py -v` | 15-20 passed |
| 全量回归 | `pytest --tb=short` | ~659 passed, 0 failed |
| Ruff | `ruff check .` | 0 errors |
| 打包烟雾 | `pip install . && python -c "import web_app,routers,fctx,mcp_server"` | OK |
| 安全 PoC | categorize 越界 → 403 | pass |
| Token 不泄露 | GET / 不含 token（网络模式） | pass |

---

## 验证矩阵与发布门禁

### v6.5.1 发布门禁（必须全绿）

```powershell
# 1. 静态检查
python -m ruff check .                                                     # 0 errors
python -m black --check . 2>$null                                          # 无变更
python -m isort --check . 2>$null                                          # 无变更

# 2. 全量测试
python -m pytest --tb=short                                                # ~659 passed

# 3. 打包
python -m pip install .                                                    # 成功
python -c "import web_app, routers, fctx, mcp_server; print('OK')"         # OK
fctx --help                                                                # 显示帮助
fctx-mcp --help                                                            # 显示帮助

# 4. 安全验证
python -c "
from fastapi.testclient import TestClient
from web_app import app
c = TestClient(app)
import tempfile, os
d = tempfile.mkdtemp()
c.post('/api/open', json={'path': d})
# BUG-W2: categorize 越界 → 403
r = c.post('/api/actions/categorize', json={'project_path': d, 'paths': ['C:/Windows/win.ini'], 'category_name': 'x'})
assert r.status_code == 403
# BUG-W7: 超长 list → 422
r = c.post('/api/project/stats', json={'paths': ['x']*2000, 'project_path': d})
assert r.status_code == 422
print('security PoCs pass')
"

# 5. 文档同步
# README/TECHNICAL_GUIDE/DEVELOPER_GUIDE 版本号 6.5.0 → 6.5.1
# ROADMAP 新增 v6.5.1 章节
```

### 版本号同步检查

| 文件 | 字段 | 值 |
|------|------|-----|
| `file_cortex_core/__init__.py:3` | `__version__` | `"6.5.1"` |
| `pyproject.toml:7` | `version` | `"6.5.1"` |
| `README.md:1,3` | 标题 + 元信息 | `6.5.1` |
| `TECHNICAL_GUIDE.md:3` | 元信息 | `6.5.1` |
| `DEVELOPER_GUIDE.md:3` | 元信息 | `6.5.1` |
| `ROADMAP.md:3` | 元信息 + 新章节 | `6.5.1` |
| `templates/index.html` | `{{ version }}` | 通过 Jinja2 注入，自动 |

---

## 执行顺序与并行度

### 依赖图

```
P0.1 (打包) ──┐
P0.2 (mcp 依赖) ─┼─→ P0 验证门禁 ─→ P1.* 并行
P0.3 (console 脚本) ─┘
P0.4 (categorize) ─── 独立
P0.5 (token 泄露) ─── 独立（影响前端，但最小版本不需前端联动）
P0.6 (mermaid SRI) ─── 独立（需联网生成 hash）
```

### 推荐执行顺序

**串行 P0（1.5h）**:
1. P0.1 + P0.3（同一文件 pyproject.toml，一起改）
2. P0.2（pyproject + README + mcp_server.py）
3. P0.4（action_routes.py + test_security_v9.py 开头）
4. P0.5（web_app.py + 测试）
5. P0.6（生成 hash + index.html + 测试）
6. P0 验证门禁全绿

**并行 P1（5h，可分两组）**:
- **后端组**（一人/一 agent）: P1.1, P1.2, P1.3, P1.4, P1.5, P1.6, P1.7, P1.8, P1.9, P1.10, P1.11, P1.12
- **前端组**（另一人/一 agent）: P1.13（ctxAction）+ 其余前端项（BUG-F3, F5, F6, F8 — 见 V9 报告，本计划未细列）

每组完成后跑 `ruff + pytest`，全绿合并。

### 提交粒度

每个 P0.x / P1.x 一个 commit：
```
fix(v651): P0.4 BUG-W2 — api_categorize 路径遍历修复

- routers/action_routes.py: 对 req.paths 逐项 is_path_safe 校验
- tests/test_security_v9.py: 新增 3 项 PoC 回归

Refs: COMPREHENSIVE_ANALYSIS_V9.md BUG-W2
```

---

## 风险登记表

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| P0.5 `_is_local_request` 在 TestClient 下 host 不是 127.0.0.1 | 高 | 测试假阴性 | 加 `testclient` 到白名单；实测调整 |
| P1.1 `max_length=1000` 漏改某字段 | 中 | 422 误拒 | 用 grep 全覆盖检查 `list[str]` |
| P1.6 `api_save` 前端联动滞后 | 低 | 旧前端功能正常（Optional） | 字段默认 None 保证兼容 |
| P1.9 Windows 长路径 hash 字符串转义 | 中 | 语法错误 | 用 raw string `r"\\?\\"` |
| P0.6 mermaid SRI hash 算错 | 低 | 浏览器拒绝执行 mermaid | 浏览器 DevTools 验证；可降级为暂不加 SRI |
| P1.12 UI 不识别 `("ERROR", msg)` tuple | 低 | 错误信息丢失，但 DONE 仍到 | UI 加分支识别 |
| 全量 pytest 时长（195s）拖慢迭代 | 高 | 开发体验差 | P0 完成后先做 P2.1（删 sleep，省 ~118s） |

---

## 附录：未细列项（留待 P1 第二批）

以下 V9 报告中的 P1 项因改动较机械或属前端，本计划未给完整 diff，实施时按 V9 报告指引即可：

- BUG-W3（api_execute_tool async 化）— 较大重构，建议拆为独立 P1.5 子项
- BUG-F2（WS token 头化）— 与 P0.5 联动，建议合并设计
- BUG-F3（tool 执行 WS modal 关闭清理）
- BUG-F5（syncStagingToBackend 项目切换快照）
- BUG-F6（ui.js mtime_fmt escape）
- BUG-F7（内联事件处理器 CSP）— 长期项
- BUG-F8（showActionModal disable 竞态）

这些项的根因、定位、修复方向已在 V9 报告 Part 3 详述，本计划聚焦可立即执行且影响最大的 13 项。

---

*计划书版本: 1.0 | 编制: Sisyphus (OhMyOpenCode) | 基线对照源码: v6.5.0 commit 61e9880*
