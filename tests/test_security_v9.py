"""Security regression tests for v6.5.1 P0/P1 fixes.

Tests cover: BUG-W1 (token leak), BUG-W2 (categorize traversal),
BUG-W5 (ProcessManager PID reuse), BUG-W6 (terminate ownership),
BUG-W7/W9 (input size limits), BUG-W10 (constant-time token compare).
"""

import pathlib

from routers.common import ProcessManager

# ── BUG-W2: api_categorize path traversal ──────────────────────────

class TestApiCategorizeTraversal:
    """BUG-W2: api_categorize must reject paths outside the project."""

    def test_categorize_rejects_path_outside_project(self, api_client, mock_project):
        """Paths outside the registered project must be 403."""
        api_client.post("/api/open", json={"path": str(mock_project)})
        outside = str(mock_project.parent / "outside_file.txt")
        (mock_project.parent / "outside_file.txt").write_text("secret", encoding="utf-8")

        # First set up a category
        api_client.post(
            "/api/project/categories",
            json={
                "project_path": str(mock_project),
                "categories": {"docs": "docs_dir"},
            },
        )

        r = api_client.post(
            "/api/actions/categorize",
            json={
                "project_path": str(mock_project),
                "paths": [outside],
                "category_name": "docs",
            },
        )
        assert r.status_code == 403, f"Expected 403, got {r.status_code}: {r.json()}"
        detail = r.json()["detail"].lower()
        assert "boundary" in detail or "unsafe" in detail, (
            f"Expected boundary/unsafe in detail: {r.json()}"
        )

    def test_categorize_rejects_dotdot_traversal(self, api_client, mock_project):
        """dot-dot traversal in paths must be rejected."""
        api_client.post("/api/open", json={"path": str(mock_project)})
        api_client.post(
            "/api/project/categories",
            json={
                "project_path": str(mock_project),
                "categories": {"x": "x_dir"},
            },
        )
        r = api_client.post(
            "/api/actions/categorize",
            json={
                "project_path": str(mock_project),
                "paths": ["../../../../etc/passwd"],
                "category_name": "x",
            },
        )
        assert r.status_code in (403, 400), (
            f"Expected 403/400, got {r.status_code}: {r.json()}"
        )

    def test_categorize_accepts_valid_within_project(self, api_client, mock_project):
        """Legitimate in-project paths must succeed."""
        api_client.post("/api/open", json={"path": str(mock_project)})
        api_client.post(
            "/api/project/categories",
            json={
                "project_path": str(mock_project),
                "categories": {"docs": "docs_dir"},
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
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.json()}"
        assert r.json()["status"] == "ok"


# ── BUG-W1: API token leak ─────────────────────────────────────────

class TestApiTokenNoLeak:
    """BUG-W1: API token must not leak via unauthenticated pages."""

    def test_index_no_token_when_api_token_set_and_remote(
        self, api_client, monkeypatch
    ):
        """Remote requests must not receive the token in HTML."""
        monkeypatch.setattr("web_app.API_TOKEN", "super-secret-xyz")
        import web_app
        monkeypatch.setattr(web_app, "_is_local_request", lambda r: False)
        r = api_client.get("/")
        assert "super-secret-xyz" not in r.text, f"Token leaked in HTML: {r.text[:500]}"

    def test_index_has_token_for_local(self, api_client, monkeypatch):
        """Local requests still get the token (backward compat)."""
        monkeypatch.setattr("web_app.API_TOKEN", "local-secret")
        import web_app
        monkeypatch.setattr(web_app, "_is_local_request", lambda r: True)
        r = api_client.get("/")
        assert "local-secret" in r.text, "Token missing for local request"

    def test_whoami_returns_version(self, api_client):
        """/api/whoami returns version info."""
        r = api_client.get("/api/whoami")
        assert r.status_code == 200
        assert "version" in r.json()


# ── BUG-W10: constant-time token comparison ────────────────────────

class TestTokenConstantTime:
    """BUG-W10: token compare must be constant-time."""

    def test_ws_token_uses_compare_digest(self):
        """Source-level: hmac.compare_digest is used in ws_routes."""
        src = (
            pathlib.Path(__file__).resolve().parent.parent
            / "routers" / "ws_routes.py"
        ).read_text(encoding="utf-8")
        assert "hmac.compare_digest" in src, "BUG-W10 not fixed in ws_routes.py"

    def test_http_token_uses_compare_digest(self):
        """Source-level: hmac.compare_digest is used in web_app."""
        src = (
            pathlib.Path(__file__).resolve().parent.parent / "web_app.py"
        ).read_text(encoding="utf-8")
        assert "hmac.compare_digest" in src, "BUG-W10 not fixed in web_app.py"

    def test_ws_rejects_empty_token_when_required(self, monkeypatch):
        """verify_ws_token rejects None/empty/wrong tokens."""
        monkeypatch.setenv("FCTX_API_TOKEN", "secret")
        from routers.ws_routes import verify_ws_token
        assert verify_ws_token(None) is False
        assert verify_ws_token("") is False
        assert verify_ws_token("wrong") is False
        assert verify_ws_token("secret") is True


# ── BUG-W7/W9: input size limits ───────────────────────────────────

class TestInputSizeLimits:
    """BUG-W7/W9: oversized inputs must be rejected."""

    def test_stats_rejects_paths_over_1000(self, api_client, mock_project):
        """More than 1000 paths must return 422."""
        api_client.post("/api/open", json={"path": str(mock_project)})
        r = api_client.post(
            "/api/project/stats",
            json={
                "paths": ["x"] * 2000,
                "project_path": str(mock_project),
            },
        )
        assert r.status_code == 422, f"Expected 422, got {r.status_code}"

    def test_session_rejects_oversized_dict(self, api_client, mock_project):
        """Oversized session data must return 400/422."""
        api_client.post("/api/open", json={"path": str(mock_project)})
        big = {str(i): "x" * 100 for i in range(10000)}
        r = api_client.post(
            "/api/project/session",
            json={
                "project_path": str(mock_project),
                "data": big,
            },
        )
        assert r.status_code in (400, 422), (
            f"Expected 400/422, got {r.status_code}"
        )

    def test_save_rejects_content_over_10mb(self, api_client, mock_project):
        """Content over 10MB must fail validation."""
        api_client.post("/api/open", json={"path": str(mock_project)})
        target = str(mock_project / "big.txt")
        # 11MB content
        r = api_client.post(
            "/api/fs/save",
            json={
                "path": target,
                "content": "x" * 11_000_000,
            },
        )
        assert r.status_code in (422, 413), f"Expected 422/413, got {r.status_code}"


# ── BUG-W5: ProcessManager PID reuse ───────────────────────────────

class TestProcessManagerPidReuse:
    """BUG-W5: register refuses to overwrite a live PID."""

    def test_register_refuses_when_pid_still_live(self):
        """Same PID with live process must be refused."""
        from unittest.mock import MagicMock

        pm = ProcessManager(max_processes=10)
        live_proc = MagicMock()
        live_proc.poll.return_value = None

        assert pm.register(1234, live_proc) is True

        new_proc = MagicMock()
        assert pm.register(1234, new_proc) is False, "Should refuse PID reuse"
        assert pm.get(1234) is live_proc, "Original must be preserved"

    def test_register_allows_when_pid_finished(self):
        """Same PID with finished process must be allowed."""
        from unittest.mock import MagicMock

        pm = ProcessManager(max_processes=10)
        dead_proc = MagicMock()
        dead_proc.poll.return_value = 0

        pm.register(1234, dead_proc)

        new_proc = MagicMock()
        assert pm.register(1234, new_proc) is True
        assert pm.get(1234) is new_proc


# ── BUG-W6: terminate process ownership ────────────────────────────

class TestTerminateProcess:
    """BUG-W6: terminate must verify process ownership."""

    def test_terminate_unknown_pid_returns_error(self, api_client):
        """Unknown PID returns error."""
        r = api_client.post("/api/actions/terminate", json={"pid": 99999999})
        assert r.status_code == 200
        assert r.json()["status"] == "error"

    def test_terminate_uses_popen_not_raw_pid(self):
        """Source-level: no unsafe os.kill(req.pid, ...) fallthrough."""
        src = (
            pathlib.Path(__file__).resolve().parent.parent
            / "routers" / "action_routes.py"
        ).read_text(encoding="utf-8")
        # After BUG-W6 fix, api_terminate_process should NOT contain:
        # - terminate_process(req.pid) (raw pid kill call)
        # - os.kill(req.pid (raw os.kill fallthrough)
        assert "terminate_process(req.pid)" not in src, (
            "BUG-W6: raw terminate_process(req.pid) still present"
        )
        assert "os.kill(req.pid" not in src, (
            "BUG-W6: raw os.kill(req.pid) still present"
        )
        # Should use proc.terminate() instead
        assert "proc.terminate()" in src, "BUG-W6: proc.terminate() missing"


# ── BUG-F1: mermaid SRI ────────────────────────────────────────────

class TestFrontendSRI:
    """BUG-F1: all CDN scripts must have SRI integrity attributes."""

    def test_all_cdn_scripts_have_integrity(self):
        """Every CDN script tag must have an integrity attribute."""
        import re

        html = (
            pathlib.Path(__file__).resolve().parent.parent
            / "templates" / "index.html"
        ).read_text(encoding="utf-8")
        cdn_scripts = re.findall(
            r'<script src="https?://[^"]+"[^>]*>', html
        )
        assert cdn_scripts, "No CDN scripts found"
        for tag in cdn_scripts:
            assert "integrity=" in tag, f"CDN script missing SRI: {tag[:120]}"
