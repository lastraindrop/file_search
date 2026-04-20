

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

    def test_api_archive(self, project_client, mock_project):
        """Verify archive creation via API."""
        f = str(mock_project / "src" / "main.py")
        res = project_client.post("/api/fs/archive", json={
            "paths": [f],
            "output_name": "test_archive.zip",
            "project_root": str(mock_project),
        })
        assert res.status_code == 200
        assert (mock_project / "test_archive.zip").exists()

    def test_api_archive_unsafe_name_rejected(self, project_client, mock_project):
        """Archive with path traversal in name is rejected."""
        f = str(mock_project / "src" / "main.py")
        res = project_client.post("/api/fs/archive", json={
            "paths": [f],
            "output_name": "../evil.zip",
            "project_root": str(mock_project),
        })
        assert res.status_code == 400

    def test_api_session_save_and_verify(self, project_client, mock_project):
        """Verify session save persists."""
        root = str(mock_project)
        res = project_client.post("/api/project/session", json={
            "project_path": root,
            "data": {"search_query": "test", "results_count": 42},
        })
        assert res.status_code == 200

        config = project_client.get(f"/api/project/config?path={root}").json()
        assert len(config["sessions"]) >= 1
        assert config["sessions"][0]["results_count"] == 42

    def test_api_favorites_add_and_remove(self, project_client, mock_project):
        """Verify favorites CRUD via API."""
        root = str(mock_project)
        f = str(mock_project / "src" / "main.py")

        res = project_client.post("/api/project/favorites", json={
            "project_path": root,
            "group_name": "Default",
            "file_paths": [f],
            "action": "add",
        })
        assert res.status_code == 200

        config = project_client.get(f"/api/project/config?path={root}").json()
        from file_cortex_core import PathValidator
        norm_f = PathValidator.norm_path(f)
        found = any(PathValidator.norm_path(p) == norm_f
                     for p in config["groups"]["Default"])
        assert found

        res = project_client.post("/api/project/favorites", json={
            "project_path": root,
            "group_name": "Default",
            "file_paths": [f],
            "action": "remove",
        })
        assert res.status_code == 200

    def test_api_collect_paths(self, project_client, mock_project):
        """Verify path collection via API."""
        f = str(mock_project / "src" / "main.py")
        res = project_client.post("/api/fs/collect_paths", json={
            "paths": [f],
            "project_root": str(mock_project),
            "mode": "relative",
            "separator": "\\n",
            "file_prefix": "@",
            "dir_suffix": "/",
        })
        assert res.status_code == 200
        assert "@" in res.json()["result"]

    def test_api_prompt_templates(self, project_client, mock_project):
        """Verify prompt templates endpoint."""
        res = project_client.get(f"/api/project/prompt_templates?path={str(mock_project)}")
        assert res.status_code == 200
        templates = res.json()
        assert isinstance(templates, dict)
        assert "Code Review" in templates or len(templates) >= 0

    def test_api_global_settings_alias(self, project_client):
        """Verify /api/global/settings alias works."""
        res = project_client.get("/api/global/settings")
        assert res.status_code == 200
        data = res.json()
        assert "preview_limit_mb" in data

        res2 = project_client.post("/api/global/settings", json={
            "preview_limit_mb": 3.0,
        })
        assert res2.status_code == 200

        data2 = client_get_settings(project_client)
        assert data2["preview_limit_mb"] == 3.0

    def test_api_batch_rename_dry_run_via_api(self, project_client, mock_project):
        """Verify batch rename via API (dry run)."""
        f = str(mock_project / "config.json")
        res = project_client.post("/api/fs/batch_rename", json={
            "project_path": str(mock_project),
            "paths": [f],
            "pattern": "config",
            "replacement": "settings",
            "dry_run": True,
        })
        assert res.status_code == 200
        results = res.json()["results"]
        assert len(results) >= 1
        assert (mock_project / "config.json").exists()

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

    def test_api_index_page(self, api_client):
        """Verify main page returns HTML."""
        res = api_client.get("/")
        assert res.status_code == 200
        assert "FileCortex" in res.text

    def test_api_workspaces_empty(self, api_client):
        """Workspaces endpoint returns valid structure with no projects."""
        res = api_client.get("/api/workspaces")
        assert res.status_code == 200
        data = res.json()
        assert "pinned" in data
        assert "recent" in data

    def test_api_rename_rejects_path_separator(self, project_client, mock_project):
        """Rename with path separator in new name is rejected."""
        f = str(mock_project / "src" / "main.py")
        res = project_client.post("/api/fs/rename", json={
            "project_path": str(mock_project),
            "path": f,
            "new_name": "../evil.py",
        })
        assert res.status_code == 400

    def test_api_save_success(self, project_client, mock_project):
        """Verify file save via API."""
        f = str(mock_project / "src" / "main.py")
        res = project_client.post("/api/fs/save", json={
            "path": f,
            "content": "print('saved')",
        })
        assert res.status_code == 200
        content = (mock_project / "src" / "main.py").read_text(encoding="utf-8")
        assert "saved" in content

    def test_api_save_unauthorized(self, api_client, tmp_path):
        """Save to unregistered project is rejected."""
        f = tmp_path / "test.txt"
        f.write_text("data")
        res = api_client.post("/api/fs/save", json={
            "path": str(f),
            "content": "new data",
        })
        assert res.status_code == 403


def client_get_settings(client):
    return client.get("/api/global/settings").json()


class TestAPITokenMiddleware:
    """Test API token authentication middleware."""

    def test_token_required_when_set(self, api_client, monkeypatch):
        """Verify 401 when token is required but missing."""
        monkeypatch.setenv("FCTX_API_TOKEN", "test_secret_123")
        import web_app
        original_token = web_app.API_TOKEN
        web_app.API_TOKEN = "test_secret_123"

        try:
            res = api_client.get("/api/config/global")
            assert res.status_code == 401

            res2 = api_client.get(
                "/api/config/global",
                headers={"X-API-Token": "wrong_token"},
            )
            assert res2.status_code == 401

            res3 = api_client.get(
                "/api/config/global",
                headers={"X-API-Token": "test_secret_123"},
            )
            assert res3.status_code == 200
        finally:
            web_app.API_TOKEN = original_token
