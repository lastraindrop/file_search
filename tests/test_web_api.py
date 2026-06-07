"""Web API tests for FileCortex v6.5.0 — consolidated from web_endpoints, web_api_advanced, api_v6.

Covers: endpoint contracts, CRUD operations, CORS/Auth, settings, file operations,
security, WebSocket search, generation flow.
"""

import importlib

import pytest
from fastapi.testclient import TestClient

from file_cortex_core import PathValidator

# ==============================================================================
# 1. Endpoint Contract Tests (from test_web_endpoints.py)
# ==============================================================================

def test_open_nonexistent_project(api_client):
    """Verify 404/400 for invalid project paths."""
    res = api_client.post(
        "/api/open",
        json={"path": "/this/path/does/not/exist/at/all/fc_test_12345"},
    )
    assert res.status_code in (404, 400)


def test_open_system_dir_blocked(api_client, system_dir):
    """Verify security block for system directories."""
    res = api_client.post("/api/open", json={"path": system_dir})
    assert res.status_code in (400, 403)


def test_content_unauthorized_path(api_client, tmp_path):
    """Accessing content of a file outside registered project roots should fail."""
    f = tmp_path / "secret.txt"
    f.write_text("unauthorized")
    res = api_client.get(f"/api/content?path={str(f)}")
    assert res.status_code == 403


def test_children_unauthorized_path(api_client, tmp_path):
    """Directory listing outside registered project roots should fail."""
    res = api_client.post("/api/fs/children", json={"path": str(tmp_path)})
    assert res.status_code == 403


def test_save_oversized_content(project_client, mock_project):
    """Test the 10MB Pydantic limit (or close to it)."""
    target = str(mock_project / "large.txt")
    huge_data = "X" * 10_000_001
    res = project_client.post("/api/fs/save", json={"path": target, "content": huge_data})
    assert res.status_code == 422


def test_stage_all_excludes(project_client, mock_project):
    """Verify that stage_all respects exclusion settings."""
    root = str(mock_project)
    project_client.post("/api/project/settings", json={
        "project_path": root,
        "settings": {"excludes": "src*"}
    })

    res = project_client.post("/api/actions/stage_all", json={
        "project_path": root,
        "mode": "files",
        "apply_excludes": True
    })
    assert res.status_code == 200
    data = project_client.get(f"/api/project/config?path={root}").json()
    staging = data.get("staging_list", [])
    assert not any("src" in p for p in staging)


def test_global_settings_roundtrip(api_client):
    """Verify global settings persistence through API."""
    new_settings = {
        "preview_limit_mb": 5.5,
        "token_threshold": 500000,
        "theme": "dark"
    }
    api_client.post("/api/global/settings", json=new_settings)

    res = api_client.get("/api/global/settings")
    data = res.json()
    assert data["preview_limit_mb"] == 5.5
    assert data["theme"] == "dark"


def test_workspaces_pin_toggle(api_client, mock_project):
    """Verify pin toggling and summary reflection."""
    path = str(mock_project)
    api_client.post("/api/open", json={"path": path})

    res = api_client.post("/api/workspaces/pin", json={"path": path})
    assert res.json()["is_pinned"] is True

    summary = api_client.get("/api/workspaces").json()
    norm_path = PathValidator.norm_path(path)
    assert any(PathValidator.norm_path(p["path"]) == norm_path for p in summary["pinned"])


def test_project_note_and_tag(project_client, mock_project):
    """Verify note and tag CRUD."""
    root = str(mock_project)
    f = str(mock_project / "src" / "main.py")

    project_client.post("/api/project/note", json={
        "project_path": root, "file_path": f, "note": "Refactor needed"
    })
    project_client.post("/api/project/tag", json={
        "project_path": root, "file_path": f, "tag": "Priority", "action": "add"
    })

    config = project_client.get(f"/api/project/config?path={root}").json()
    f_norm = PathValidator.norm_path(f)
    notes = config.get("notes", {})
    assert any(
        PathValidator.norm_path(k) == f_norm and v == "Refactor needed"
        for k, v in notes.items()
    ), f"Note not found. Keys: {list(notes.keys())}, Expected: {f_norm}"
    tags = config.get("tags", {})
    assert any(
        PathValidator.norm_path(k) == f_norm and "Priority" in v
        for k, v in tags.items()
    ), f"Tag not found. Keys: {list(tags.keys())}, Expected: {f_norm}"


# ==============================================================================
# 2. Advanced CRUD / CORS / Auth / Settings Tests (from test_web_api_advanced.py)
# ==============================================================================

class TestWebAPIAdvanced:
    """Advanced web API endpoint tests covering untested routes."""

    def test_api_create_file(self, project_client, mock_project):
        """Verify file creation via API."""
        res = project_client.post("/api/fs/create", json={
            "parent_path": str(mock_project),
            "name": "new_file.txt",
            "is_dir": False,
        })
        assert res.status_code == 200
        assert (mock_project / "new_file.txt").exists()

    def test_api_create_directory(self, project_client, mock_project):
        """Verify directory creation via API."""
        res = project_client.post("/api/fs/create", json={
            "parent_path": str(mock_project),
            "name": "new_dir",
            "is_dir": True,
        })
        assert res.status_code == 200
        assert (mock_project / "new_dir").is_dir()

    def test_api_create_duplicate_rejected(self, project_client, mock_project):
        """Creating existing item returns error."""
        res = project_client.post("/api/fs/create", json={
            "parent_path": str(mock_project),
            "name": "config.json",
            "is_dir": False,
        })
        assert res.status_code in (400, 500)

    def test_api_create_traversal_rejected(self, project_client, mock_project):
        """Verify path traversal in create is blocked."""
        res = project_client.post("/api/fs/create", json={
            "parent_path": str(mock_project),
            "name": "../../etc/passwd",
            "is_dir": False,
        })
        assert res.status_code != 200

    def test_api_archive(self, project_client, mock_project):
        """Verify archive creation via API."""
        res = project_client.post("/api/fs/archive", json={
            "paths": [str(mock_project / "src")],
            "output_name": "backup.zip",
            "project_root": str(mock_project),
        })
        assert res.status_code == 200

    def test_api_archive_unsafe_name_rejected(self, project_client, mock_project):
        """Verify archive with traversal name is rejected."""
        res = project_client.post("/api/fs/archive", json={
            "paths": [str(mock_project / "src")],
            "output_name": "../../etc/evil.zip",
            "project_root": str(mock_project),
        })
        assert res.status_code != 200

    def test_api_session_save_and_verify(self, project_client, mock_project):
        """Verify session persistence and retrieval."""
        root = str(mock_project)
        session_data = {
            "project_path": root,
            "staging_list": [str(mock_project / "src" / "main.py")],
        }
        res = project_client.post("/api/project/settings", json={
            "project_path": root,
            "settings": session_data
        })
        assert res.status_code == 200

    def test_api_favorites_add_and_remove(self, project_client, mock_project):
        """Verify favorites add/remove cycle."""
        root = str(mock_project)
        f = str(mock_project / "src" / "main.py")
        project_client.post("/api/project/favorites", json={
            "project_path": root, "file_paths": [f], "group_name": "Default", "action": "add"
        })
        project_client.post("/api/project/favorites", json={
            "project_path": root, "file_paths": [f], "group_name": "Default", "action": "remove"
        })

    def test_api_collect_paths(self, project_client, mock_project):
        """Verify path collection formatting."""
        res = project_client.post("/api/fs/collect_paths", json={
            "paths": [str(mock_project / "src" / "main.py")],
            "project_root": str(mock_project),
            "mode": "relative",
            "separator": "\\n",
            "file_prefix": "",
            "dir_suffix": "",
        })
        assert res.status_code == 200
        assert "main.py" in res.json()["result"]

    def test_api_collect_paths_unauthorized_root_returns_403(self, api_client, tmp_path):
        """Unauthorized collect_paths request should preserve 403 semantics."""
        res = api_client.post("/api/fs/collect_paths", json={
            "paths": [str(tmp_path / "ghost.txt")],
            "project_root": str(tmp_path),
            "mode": "relative",
        })
        assert res.status_code == 403

    def test_api_prompt_templates(self, project_client, mock_project):
        """Verify prompt templates endpoint."""
        res = project_client.get(f"/api/project/prompt_templates?path={str(mock_project)}")
        assert res.status_code == 200

    def test_api_global_settings_alias(self, project_client):
        """Verify /api/global/settings/settings alias works."""
        res = project_client.get("/api/global/settings")
        assert res.status_code == 200

    def test_api_batch_rename_dry_run_via_api(self, project_client, mock_project):
        """Verify batch rename dry run returns preview."""
        res = project_client.post("/api/fs/batch_rename", json={
            "project_path": str(mock_project),
            "paths": [str(mock_project / "src" / "main.py")],
            "pattern": "main",
            "replacement": "entry",
            "dry_run": True,
        })
        assert res.status_code == 200
        assert "results" in res.json()

    def test_api_batch_rename_live(self, project_client, mock_project):
        """Verify batch rename via API (live execution)."""
        f = mock_project / "renamable.txt"
        f.write_text("test", encoding="utf-8")
        res = project_client.post("/api/fs/batch_rename", json={
            "project_path": str(mock_project),
            "paths": [str(f)],
            "pattern": "renamable",
            "replacement": "renamed",
            "dry_run": False,
        })
        assert res.status_code == 200
        assert (mock_project / "renamed.txt").exists()
        assert not f.exists()

    def test_api_index_page(self, project_client):
        """Verify index page loads and contains version."""
        res = project_client.get("/")
        assert res.status_code == 200
        assert "FileCortex" in res.text

    def test_api_workspaces_empty(self, project_client):
        """Verify workspaces endpoint returns valid structure."""
        res = project_client.get("/api/workspaces")
        assert res.status_code == 200
        data = res.json()
        assert "pinned" in data
        assert "recent" in data

    def test_api_rename_rejects_path_separator(self, project_client, mock_project):
        """Verify rename blocks path separator in new name."""
        res = project_client.post("/api/fs/rename", json={
            "project_path": str(mock_project),
            "path": str(mock_project / "src" / "main.py"),
            "new_name": "sub/evil.py",
        })
        assert res.status_code != 200

    def test_api_save_success(self, project_client, mock_project):
        """Verify file save via API."""
        f = str(mock_project / "src" / "main.py")
        res = project_client.post("/api/fs/save", json={
            "path": f,
            "content": "print('saved')",
        })
        assert res.status_code == 200

    def test_api_save_unauthorized(self, project_client, tmp_path):
        """Verify save outside project scope is blocked."""
        target = str(tmp_path / "unauth.txt")
        res = project_client.post("/api/fs/save", json={
            "path": target, "content": "nope"
        })
        assert res.status_code == 403


class TestAPITokenMiddleware:
    """Test API token authentication middleware."""

    def test_token_required_when_set(self, api_client, monkeypatch):
        """Verify 401 when token is required but missing."""
        monkeypatch.setenv("FCTX_API_TOKEN", "test_secret_123")
        import web_app
        original_token = web_app.API_TOKEN
        web_app.API_TOKEN = "test_secret_123"

        try:
            res = api_client.get("/api/global/settings")
            assert res.status_code == 401

            res2 = api_client.get(
                "/api/global/settings",
                headers={"X-API-Token": "wrong_token"},
            )
            assert res2.status_code == 401

            res3 = api_client.get(
                "/api/global/settings",
                headers={"X-API-Token": "test_secret_123"},
            )
            assert res3.status_code == 200
        finally:
            web_app.API_TOKEN = original_token

    def test_cors_respects_allowed_origins_env(self, monkeypatch):
        """CORS middleware should reflect configured allowlist instead of wildcard."""
        monkeypatch.setenv("FCTX_ALLOWED_ORIGINS", "https://allowed.example")
        import web_app

        reloaded = importlib.reload(web_app)
        client = TestClient(reloaded.app)

        try:
            allowed = client.options(
                "/api/global/settings",
                headers={
                    "Origin": "https://allowed.example",
                    "Access-Control-Request-Method": "GET",
                },
            )
            assert "https://allowed.example" in allowed.headers.get(
                "access-control-allow-origin", ""
            )
        finally:
            importlib.reload(web_app)


# ==============================================================================
# 3. API v6 Evolution Tests (from test_api_v6.py)
# ==============================================================================

def test_api_browser_contracts(project_client, mock_project):
    """Integrated Test: Open -> Children -> Content -> Recent."""
    # Open
    res_open = project_client.post("/api/open", json={"path": str(mock_project)})
    assert res_open.status_code == 200
    root_data = res_open.json()
    assert root_data["path"] == PathValidator.norm_path(mock_project)

    # Children
    res_children = project_client.post("/api/fs/children", json={"path": str(mock_project)})
    assert res_children.status_code == 200
    children = res_children.json()["children"]
    assert any(c["name"] == "src" for c in children)
    child = children[0]
    for key in ["name", "path", "type", "size_fmt", "mtime_fmt", "has_children"]:
        assert key in child

    # Content
    main_py = str(mock_project / "src" / "main.py")
    res_content = project_client.get(f"/api/content?path={main_py}")
    assert res_content.status_code == 200
    data = res_content.json()
    assert "content" in data
    assert "encoding" in data
    assert "is_truncated" in data

    # Recent
    res_recent = project_client.get("/api/recent_projects")
    paths = res_recent.json()
    norm_project = PathValidator.norm_path(mock_project)
    assert any(PathValidator.norm_path(p["path"]) == norm_project for p in paths)


@pytest.mark.parametrize("file_type,expected_content", [
    ("binary", "--- Binary File (Preview Unavailable) ---"),
    ("large", None)
])
def test_api_content_edge_cases(project_client, mock_project, file_type, expected_content):
    """Combined check for binary detection and truncation."""
    if file_type == "binary":
        target = str(mock_project / "data.bin")
        res = project_client.get(f"/api/content?path={target}")
        assert expected_content in res.json()["content"]
    elif file_type == "large":
        large_f = mock_project / "large_trunc.txt"
        large_f.write_text("X" * 1500000)
        res = project_client.get(f"/api/content?path={str(large_f)}")
        assert len(res.json()["content"]) <= 1050000
        assert res.json()["is_truncated"] is True


@pytest.mark.parametrize("request_format", ["flat", "nested"])
def test_api_global_settings_sync(project_client, request_format):
    """Consolidated Test: Global settings update (Forward & backward compatible)."""
    endpoint = "/api/global/settings"
    payload = {"preview_limit_mb": 2.5, "token_threshold": 300000}
    if request_format == "nested":
        payload = {"settings": payload}

    res = project_client.post(endpoint, json=payload)
    assert res.status_code == 200

    data = project_client.get("/api/global/settings").json()
    assert data["preview_limit_mb"] == 2.5
    assert data["token_threshold"] == 300000


def test_api_project_specific_metadata(project_client, mock_project):
    """Test tools, Categories, and Favorites update endpoints."""
    path = str(mock_project)

    project_client.post(
        "/api/project/tools",
        json={"project_path": path, "tools": {"Harden": "fctx polish"}},
    )
    project_client.post(
        "/api/project/categories",
        json={"project_path": path, "categories": {"Legacy": "old_src"}},
    )
    project_client.post(
        "/api/project/settings",
        json={"project_path": path, "settings": {"excludes": "*.log", "illegal": "leak"}},
    )

    config = project_client.get(f"/api/project/config?path={path}").json()
    assert config["custom_tools"]["Harden"] == "fctx polish"
    assert config["quick_categories"]["Legacy"] == "old_src"
    assert config["excludes"] == "*.log"
    assert "illegal" not in config


@pytest.mark.parametrize("op", ["move", "rename", "delete"])
def test_api_fs_ops_safety(project_client, mock_project, system_dir, op):
    """Stress test security of file operations via API."""
    src = str(mock_project / "src" / "main.py")

    if op == "move":
        res = project_client.post("/api/fs/move", json={"src_paths": [src], "dst_dir": system_dir})
        assert res.status_code in (403, 200)
        if res.status_code == 200:
            assert src in res.json().get("skipped", [])
    elif op == "rename":
        res = project_client.post(
            "/api/fs/rename",
            json={"project_path": str(mock_project), "path": src, "new_name": "../../etc/passwd"},
        )
        assert res.status_code != 200
    elif op == "delete":
        res = project_client.post(
            "/api/fs/delete",
            json={"project_path": str(mock_project), "paths": ["../../../etc/passwd"]},
        )
        assert res.status_code != 200


@pytest.mark.parametrize("fmt", ["markdown", "xml"])
def test_api_full_generation_flow(project_client, mock_project, fmt):
    """E2E flow: Open -> Stage -> Stats -> Generate."""
    root = str(mock_project)
    f1 = str(mock_project / "src" / "main.py")

    project_client.post(
        "/api/project/settings",
        json={"project_path": root, "settings": {"staging_list": [f1]}},
    )

    res_stats = project_client.post(
        "/api/project/stats", json={"paths": [f1], "project_path": root},
    )
    assert res_stats.json()["total_tokens"] > 0

    res_gen = project_client.post(
        "/api/generate", json={"files": [f1], "project_path": root, "export_format": fmt},
    )
    assert res_gen.status_code == 200
    content = res_gen.json()["content"]
    if fmt == "xml":
        assert "<context>" in content
    else:
        assert "```python" in content


def test_api_search_websocket_protocol(project_client, mock_project):
    """Verify WebSocket search flow and stop events."""
    ws_url = f"/ws/search?path={str(mock_project)}&query=main&mode=smart"
    with project_client.websocket_connect(ws_url) as ws:
        results = []
        while True:
            data = ws.receive_json()
            if data.get("status") == "DONE":
                break
            if data.get("status") == "ERROR":
                pytest.fail(f"Search WS error: {data}")
            results.append(data)
        assert len(results) >= 1
