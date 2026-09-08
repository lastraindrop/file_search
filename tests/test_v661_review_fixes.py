"""v6.6.1 review-driven bugfix round regression tests.

Anchors for the 19-fix review round: WS origin gate, resolved-root config
lookup, WS success-path PID hygiene, CLI project-relative paths and exit
codes, global-settings bounds, and desktop/frontend source contracts.
"""

import re
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from starlette.websockets import WebSocketDisconnect

import web_app
from file_cortex_core import DataManager, PathValidator

ROOT = Path(__file__).resolve().parent.parent


# ==============================================================================
# 1. WS origin gate (CSWSH fix)
# ==============================================================================


class TestWsOriginGate:
    """WebSocket handshakes must apply the HTTP middleware's origin policy."""

    def test_foreign_origin_search_rejected(
        self, project_client, mock_project
    ):
        """A cross-site Origin must be closed with 4001, not streamed data."""
        ws_url = f"/ws/search?path={str(mock_project)}&query=main"
        with pytest.raises(WebSocketDisconnect) as exc_info, \
                project_client.websocket_connect(
                    ws_url, headers={"Origin": "http://evil.example"}
                ) as ws:
            ws.receive_json()
        assert exc_info.value.code == 4001

    def test_foreign_origin_execute_rejected(self, project_client):
        """The tool stream endpoint must be gated identically."""
        ws_url = (
            "/ws/actions/execute?project_path=E:%5Cnowhere"
            "&tool_name=T&path=E:%5Cnowhere%5Cx"
        )
        with pytest.raises(WebSocketDisconnect) as exc_info, \
                project_client.websocket_connect(
                    ws_url, headers={"Origin": "http://evil.example"}
                ) as ws:
            ws.receive_json()
        assert exc_info.value.code == 4001

    @pytest.mark.parametrize("origin", [None, "http://127.0.0.1:8000"])
    def test_local_or_missing_origin_allowed(
        self, project_client, mock_project, origin
    ):
        """Loopback origins and non-browser clients (no Origin) pass."""
        headers = {"Origin": origin} if origin else {}
        ws_url = f"/ws/search?path={str(mock_project)}&query=main"
        with project_client.websocket_connect(ws_url, headers=headers) as ws:
            frame = ws.receive_json()
        assert isinstance(frame, dict)

    def test_origin_helper_unit_semantics(self, monkeypatch):
        """_origin_allowed: wildcard wins, loopback hosts pass, others fail."""
        assert web_app._origin_allowed("http://evil.example") is False
        assert web_app._origin_allowed("http://localhost:9999") is True
        assert web_app._origin_allowed("http://[::1]:8080") is True
        monkeypatch.setattr(web_app, "ALLOWED_ORIGINS", ["*"])
        assert web_app._origin_allowed("https://anywhere.dev") is True


# ==============================================================================
# 2. Config lookup must use the RESOLVED root (no phantom registration)
# ==============================================================================


class TestExecuteUsesResolvedRoot:
    """get_project_data must use the registered root, never a raw subdir.

    A raw subdirectory would auto-register a phantom project entry and
    resolve tools against that entry's defaults.
    """

    @pytest.fixture
    def get_project_data_spy(self, monkeypatch):
        """Captures every DataManager.get_project_data path argument."""
        calls = []
        original = DataManager.get_project_data

        def spy(self, path_str):
            calls.append(path_str)
            return original(self, path_str)

        monkeypatch.setattr(DataManager, "get_project_data", spy)
        return calls

    def test_http_execute_resolves_root(
        self, project_client, mock_project, get_project_data_spy
    ):
        """Subdirectory project_path resolves to the parent registered root."""
        subdir = mock_project / "src"
        res = project_client.post(
            "/api/actions/execute",
            json={
                "project_path": str(subdir),
                "tool_name": "Nope",
                "paths": [],
            },
        )
        assert res.status_code == 404
        root_norm = PathValidator.norm_path(str(mock_project))
        subdir_norm = PathValidator.norm_path(str(subdir))
        assert root_norm in get_project_data_spy
        assert subdir_norm not in get_project_data_spy

    def test_ws_execute_resolves_root(
        self, project_client, mock_project, get_project_data_spy
    ):
        """The WS tool stream must show the same resolved-root behavior."""
        subdir = mock_project / "src"
        ws_url = (
            f"/ws/actions/execute?project_path={subdir}"
            f"&tool_name=Nope&path={mock_project / 'src' / 'main.py'}"
        )
        with project_client.websocket_connect(ws_url) as ws:
            frame = ws.receive_json()
        assert frame == {"status": "ERROR", "msg": "Tool template not found"}
        root_norm = PathValidator.norm_path(str(mock_project))
        subdir_norm = PathValidator.norm_path(str(subdir))
        assert root_norm in get_project_data_spy
        assert subdir_norm not in get_project_data_spy


# ==============================================================================
# 3. WS tool stream: success path must not taskkill the finished PID
# ==============================================================================


class TestWsToolStreamSuccessNoTerminate:
    """A finished process must not be terminated post-exit.

    Terminating a dead PID wastes a taskkill spawn and risks killing an
    unrelated process if the OS reused the PID.
    """

    def test_success_frame_and_no_terminate(
        self, project_client, mock_project, monkeypatch
    ):
        """A clean run delivers exit_code=0 and never calls terminate."""
        res = project_client.post(
            "/api/project/tools",
            json={
                "project_path": str(mock_project),
                "tools": {"Echo": f'"{sys.executable}" -c "print(42)"'},
            },
        )
        assert res.status_code == 200

        terminate_calls = []
        monkeypatch.setattr(
            "routers.ws_routes.terminate_process",
            lambda pid: terminate_calls.append(pid),
        )

        ws_url = (
            f"/ws/actions/execute?project_path={mock_project}"
            f"&tool_name=Echo&path={mock_project / 'src' / 'main.py'}"
        )
        exit_frame = None
        saw_done = False
        with project_client.websocket_connect(ws_url) as ws:
            while not saw_done:
                frame = ws.receive_json()
                if "exit_code" in frame:
                    exit_frame = frame
                if frame.get("status") == "DONE":
                    saw_done = True

        assert exit_frame is not None and exit_frame["exit_code"] == 0
        assert terminate_calls == []


# ==============================================================================
# 4. CLI: project-relative paths, relative display, limit clamp, exit codes
# ==============================================================================


class TestCliReviewFixes:
    """CLI relative-path anchoring, display, limit clamp, exit codes."""

    def test_resolve_in_project_anchors_relative_paths(self):
        """Relative args anchor to the project root; absolutes pass through."""
        import fctx

        root = PathValidator.norm_path("E:/some/proj")
        resolved = fctx._resolve_in_project("src/main.py", root)
        assert resolved == root + "/src/main.py"
        absolute = fctx._resolve_in_project("E:/other/file.py", root)
        assert absolute == PathValidator.norm_path("E:/other/file.py")

    def test_cmd_stage_accepts_project_relative_path(
        self, clean_config, mock_project, tmp_path, monkeypatch, capsys
    ):
        """Relative paths must anchor to the project root, not the CWD."""
        import argparse

        import fctx

        cwd_dir = tmp_path / "unrelated_cwd"
        cwd_dir.mkdir()
        monkeypatch.chdir(cwd_dir)

        # Registration is required before resolve_project_root() can match.
        clean_config.get_project_data_obj(str(mock_project))

        args = argparse.Namespace(
            project=str(mock_project), path="src/main.py"
        )
        assert fctx.cmd_stage(args, clean_config) is True
        expected = PathValidator.norm_path(str(mock_project / "src" / "main.py"))
        assert expected in clean_config.get_project_data_obj(
            PathValidator.norm_path(str(mock_project))
        ).staging_list

    def test_cmd_search_displays_relative_paths(
        self, clean_config, mock_project, capsys
    ):
        """Match lines must show project-relative, normalized paths."""
        import argparse

        import fctx

        clean_config.get_project_data_obj(str(mock_project))
        args = argparse.Namespace(
            project=str(mock_project),
            query="main",
            mode="smart",
            excludes="",
            limit=50,
        )
        assert fctx.cmd_search(args, clean_config) is True
        out = capsys.readouterr().out
        match_lines = [line for line in out.splitlines() if "[Match]" in line]
        assert match_lines, "expected at least one match line"
        assert all("main.py" in line for line in match_lines)
        assert all("mock_project" not in line for line in match_lines)

    def test_cmd_search_limit_zero_is_clamped(
        self, clean_config, mock_project, capsys
    ):
        """limit=0 must behave like a small positive limit, not misbehave."""
        import argparse

        import fctx

        clean_config.get_project_data_obj(str(mock_project))
        args = argparse.Namespace(
            project=str(mock_project),
            query="main",
            mode="smart",
            excludes="",
            limit=0,
        )
        assert fctx.cmd_search(args, clean_config) is True
        assert "Total:" in capsys.readouterr().out

    def test_cmd_run_reflects_execution_errors(
        self, clean_config, mock_project, monkeypatch, capsys
    ):
        """A tool that fails to run must flip the CLI exit code to 1."""
        import argparse

        import fctx
        from file_cortex_core import ActionBridge

        proj_root_norm = PathValidator.norm_path(str(mock_project))
        proj = clean_config.get_project_data_obj(proj_root_norm)
        proj.staging_list = [
            PathValidator.norm_path(str(mock_project / "src" / "main.py"))
        ]
        proj.custom_tools = {"Broken": "whatever {path}"}

        args = argparse.Namespace(project=str(mock_project), tool="Broken")
        monkeypatch.setattr(
            ActionBridge, "execute_tool",
            staticmethod(lambda *a, **k: {"error": "boom"}),
        )
        assert fctx.cmd_run(args, clean_config) is False

        monkeypatch.setattr(
            ActionBridge, "execute_tool",
            staticmethod(lambda *a, **k: {"exit_code": 0}),
        )
        assert fctx.cmd_run(args, clean_config) is True


# ==============================================================================
# 5. Global settings schema bounds (hardening parity)
# ==============================================================================


class TestGlobalSettingsBounds:
    """Global-settings request fields carry the same bounds as their peers."""

    def test_oversized_settings_dict_rejected(self, api_client):
        """A settings dict over the 100KB budget must be a 422."""
        res = api_client.post(
            "/api/global/settings",
            json={"settings": {"big": "x" * 200_000}},
        )
        assert res.status_code == 422

    def test_oversized_theme_rejected(self, api_client):
        """A theme beyond 64 chars must be a 422."""
        res = api_client.post(
            "/api/global/settings",
            json={"theme": "x" * 65},
        )
        assert res.status_code == 422


# ==============================================================================
# 6. Desktop + frontend source contracts (no GUI behavioral harness yet)
# ==============================================================================


class TestTestIsolationGuard:
    """CLI entry-point tests must never touch the real ~/.filecortex config."""

    def test_cli_open_writes_isolated_config(self, mock_project):
        """Fctx open runs against the per-test isolated config file."""
        import fctx
        from file_cortex_core import config as config_mod

        with patch("sys.argv", ["fctx", "open", str(mock_project)]):
            fctx.main()

        assert config_mod._CONFIG_FILE is not None
        assert config_mod._CONFIG_FILE.name == "isolated_config.json"
        assert config_mod._CONFIG_FILE.exists()


class TestReviewFixSourceContracts:
    """Source-level anchors for GUI-layer fixes (no behavioral harness yet)."""

    def test_desktop_fixes_present(self):
        """Staging menu bind, poll-chain guard, tool guard, stats cap."""
        source = (ROOT / "file_search.py").read_text(encoding="utf-8")
        # The generic Button-3 loop must NOT include tree_staging: Tk bind()
        # replaces handlers and would kill the dedicated staging menu.
        loop = re.search(
            r"for t in \[\s*self\.tree_search,\s*self\.tree_fav,"
            r"\s*self\.tree_proj,?\s*\]",
            source,
        )
        assert loop, "generic context-menu bind loop drifted"
        assert "self.staging_menu.post" in source
        assert "_poll_after_id" in source
        assert "_tool_run_in_flight" in source
        assert "read_cap = 1024 * 1024" in source

    def test_frontend_fixes_present(self):
        """WS terminal states, generation guard, change-driven controls."""
        main_js = (ROOT / "static" / "js" / "main.js").read_text(
            encoding="utf-8"
        )
        events_js = (ROOT / "static" / "js" / "events.js").read_text(
            encoding="utf-8"
        )
        state_js = (ROOT / "static" / "js" / "state.js").read_text(
            encoding="utf-8"
        )
        api_js = (ROOT / "static" / "js" / "api.js").read_text(
            encoding="utf-8"
        )
        assert "data.status === 'ERROR'" in main_js
        assert "socket.onclose" in main_js
        assert "openProjectSeq" in main_js and "openProjectSeq" in state_js
        assert "action === 'toggleSelectAll') return" in events_js
        assert "tagName === 'SELECT') return" in events_js
        assert "_postJson(config.endpoints.terminate" in api_js
        assert "saveProjectTools" not in api_js
        assert "renderSearchResultItem" not in (
            ROOT / "static" / "js" / "ui.js"
        ).read_text(encoding="utf-8")
