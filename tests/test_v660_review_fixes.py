"""v6.6.0 review-driven hardening regression suite.

Each test pins one fix from the v6.6.0 architecture/code review round:

- P1 security: UNC long-prefix bypass, note/tag auto-registration bypass,
  MCP --transport wiring, POSIX process-group self-kill, corrupt-config
  rewrite data loss.
- P2 robustness: search CancelledError escape, backpressure cancellation,
  manual-exclude sub-path patterns, get_metadata fallback contract,
  WS search crash masquerading as DONE, duplicate-worker cancel sentinel,
  WS auth close-code delivery.
- P3 polish: schema literals/bounds, CLI exit codes, archive-source
  hygiene, search-limit validation.
"""

import concurrent.futures
import os
import pathlib
import queue as queue_mod
import subprocess
import sys
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

import mcp_server
import web_app
from file_cortex_core import (
    DataManager,
    DuplicateWorker,
    FileOps,
    FileUtils,
    PathValidator,
    SearchWorker,
    search_generator,
)
from file_cortex_core import search as search_mod
from file_cortex_core.search import SearchQuery

# ==============================================================================
# 1. P1 security fixes
# ==============================================================================


class TestUncLongPrefixBypass:
    r"""security.py: \\?\UNC\server\share must be rejected like \\server\share."""

    @pytest.mark.skipif(os.name != "nt", reason="Windows UNC semantics")
    def test_validate_project_rejects_unc_long_prefix(self):
        r"""validate_project must reject the \\?\UNC long-path form."""
        with pytest.raises(PermissionError, match="UNC"):
            PathValidator.validate_project("\\\\?\\UNC\\evil\\share\\data")

    @pytest.mark.skipif(os.name != "nt", reason="Windows UNC semantics")
    def test_validate_project_rejects_plain_unc(self):
        """validate_project must reject plain UNC paths."""
        with pytest.raises(PermissionError, match="UNC"):
            PathValidator.validate_project("\\\\evil\\share\\data")

    def test_is_safe_rejects_unc_target(self):
        """is_safe must reject UNC targets."""
        assert PathValidator.is_safe("\\\\evil\\share\\x", "C:\\proj") is False

    def test_is_safe_rejects_unc_long_prefix_target(self):
        r"""is_safe must reject the \\?\UNC long-path form of UNC targets."""
        assert PathValidator.is_safe("\\\\?\\UNC\\evil\\share\\x", "C:\\proj") is False


class TestNoteTagRegistrationBypass:
    """/api/project/note and /api/project/tag must not auto-register projects."""

    def test_note_requires_registered_project(self, api_client, mock_project):
        """Unregistered project paths must be refused, not auto-registered."""
        unregistered = mock_project  # exists on disk but never /api/open-ed
        res = api_client.post(
            "/api/project/note",
            json={
                "project_path": str(unregistered),
                "file_path": str(unregistered / "src" / "main.py"),
                "note": "hello",
            },
        )
        assert res.status_code == 403
        dm = DataManager()
        assert PathValidator.norm_path(str(unregistered)) not in dm.config.projects

    def test_tag_requires_registered_project(self, api_client, mock_project):
        """Unregistered project paths must be refused for tag mutations."""
        res = api_client.post(
            "/api/project/tag",
            json={
                "project_path": str(mock_project),
                "file_path": str(mock_project / "src" / "main.py"),
                "tag": "keep",
                "action": "add",
            },
        )
        assert res.status_code == 403
        dm = DataManager()
        assert PathValidator.norm_path(str(mock_project)) not in dm.config.projects

    def test_note_succeeds_for_registered_project(self, project_client, mock_project):
        """Registered projects keep working after adding the gate."""
        res = project_client.post(
            "/api/project/note",
            json={
                "project_path": str(mock_project),
                "file_path": str(mock_project / "src" / "main.py"),
                "note": "hello",
            },
        )
        assert res.status_code == 200
        assert res.json()["status"] == "ok"


class TestExtractUncSource:
    """UNC archive sources must be rejected before any filesystem touch."""

    def test_core_rejects_unc_archive(self, mock_project, tmp_path):
        """extract_archive must raise before touching the network path."""
        dst = tmp_path / "out"
        with pytest.raises(PermissionError, match="UNC"):
            FileOps.extract_archive(
                "\\\\?\\UNC\\evil\\share\\payload.zip", str(dst), str(mock_project)
            )

    def test_api_rejects_unc_archive(self, project_client, mock_project):
        """The Web route must reject UNC zip sources with 403."""
        res = project_client.post(
            "/api/fs/extract",
            json={
                "project_root": str(mock_project),
                "zip_path": "\\\\evil\\share\\payload.zip",
                "dst_dir": str(mock_project / "out"),
            },
        )
        assert res.status_code == 403


class TestMcpTransportWiring:
    """mcp_server.main() must forward --transport to FastMCP.run()."""

    def _run_main_with(self, monkeypatch, argv):
        """Runs main() against a fake server, capturing run() kwargs."""
        captured = {}

        class FakeServer:
            def run(self, **kwargs):
                captured.update(kwargs)

        monkeypatch.setattr(mcp_server, "get_mcp", lambda: FakeServer())
        monkeypatch.setattr(mcp_server, "_MCP_SDK_AVAILABLE", True)
        monkeypatch.setattr(sys, "argv", ["mcp_server.py"] + argv)
        mcp_server.main()
        return captured

    def test_stdio_passes_no_transport(self, monkeypatch):
        """Stdio must call run() without transport kwargs."""
        captured = self._run_main_with(monkeypatch, ["--transport", "stdio"])
        assert captured == {}

    def test_http_alias_maps_to_streamable_http(self, monkeypatch):
        """The legacy 'http' alias must map onto 'streamable-http'."""
        captured = self._run_main_with(
            monkeypatch,
            ["--transport", "http", "--host", "0.0.0.0", "--port", "9000"],
        )
        assert captured.get("transport") == "streamable-http"
        assert captured.get("host") == "0.0.0.0"
        assert captured.get("port") == 9000

    def test_streamable_http_direct(self, monkeypatch):
        """The SDK literal must be forwarded unchanged."""
        captured = self._run_main_with(monkeypatch, ["--transport", "streamable-http"])
        assert captured.get("transport") == "streamable-http"


class TestExecuteToolProcessGroup:
    """execute_tool must detach from the server's process group on POSIX."""

    def test_start_new_session_flag(self, mock_project):
        """Popen must be created with start_new_session on POSIX only."""
        from file_cortex_core import ActionBridge
        from file_cortex_core import actions as actions_mod

        captured_kwargs = {}
        fake_proc = MagicMock()
        fake_proc.pid = 43210
        fake_proc.communicate.return_value = ("", "")
        fake_proc.__enter__.return_value = fake_proc
        fake_proc.__exit__.return_value = False

        def fake_popen(*args, **kwargs):
            captured_kwargs.update(kwargs)
            return fake_proc

        with patch.object(actions_mod.subprocess, "Popen", fake_popen):
            result = ActionBridge.execute_tool(
                "python -c pass",
                str(mock_project / "src" / "main.py"),
                str(mock_project),
            )
        assert result["status"] in ("success", "error")
        assert captured_kwargs.get("start_new_session") is (os.name != "nt")


class TestShutdownTrackedProcesses:
    """web_app lifespan must terminate still-tracked subprocesses."""

    def test_tracked_live_process_is_terminated(self, monkeypatch):
        """Live processes are terminated; exited ones are just unregistered."""
        from routers import common as route_common

        terminated = []
        monkeypatch.setattr(
            "file_cortex_core.process_utils.terminate_process",
            lambda pid: terminated.append(pid),
        )
        live = MagicMock()
        live.poll.return_value = None  # still running
        dead = MagicMock()
        dead.poll.return_value = 0  # exited

        route_common.process_manager.register(111, live)
        route_common.process_manager.register(222, dead)

        web_app._shutdown_tracked_processes()

        assert terminated == [111]
        assert route_common.process_manager.pids == []


# ==============================================================================
# 2. Config integrity (P1)
# ==============================================================================


class TestCorruptConfigBackup:
    """Rewriting a corrupt config must preserve the original as a backup."""

    def test_corrupt_disk_config_backed_up(self, clean_config, tmp_path):
        """A .corrupt-<timestamp> copy must exist after the rewrite."""
        config_path = clean_config.config_path
        garbage = "{ this is not valid json !!!"
        config_path.write_text(garbage, encoding="utf-8")

        clean_config.add_to_recent(str(tmp_path))  # triggers save()

        backups = list(config_path.parent.glob("*.corrupt-*"))
        assert backups, "corrupt config was rewritten without a backup"
        assert backups[0].read_text(encoding="utf-8") == garbage


class TestProjectDataObjGuard:
    r"""get_project_data_obj must refuse to create a \"\" project key."""

    def test_empty_path_raises(self, clean_config):
        """Empty strings must raise, not create a '' project key."""
        with pytest.raises(ValueError, match="empty"):
            clean_config.get_project_data_obj("")

    def test_none_path_raises(self, clean_config):
        """None must raise, not create a '' project key."""
        with pytest.raises(ValueError, match="empty"):
            clean_config.get_project_data_obj(None)


# ==============================================================================
# 3. Search robustness (P2)
# ==============================================================================


class TestSearchCancelledFuture:
    """A cancelled shared-pool future must not kill the search generator."""

    def test_generator_survives_cancelled_futures(self, stress_project):
        """Pre-cancelled futures must be drained, not hang or crash."""
        cancelled_future = concurrent.futures.Future()
        cancelled_future.cancel()

        with patch.object(
            search_mod, "_submit_content_task", lambda *a, **k: cancelled_future
        ):
            results = list(
                search_generator(stress_project, "target", "content", "", False, True)
            )
        # All content futures were cancelled -> no content matches, but the
        # generator must terminate cleanly instead of raising/hanging.
        assert isinstance(results, list)

    def test_worker_always_emits_done(self, stress_project):
        """SearchWorker must always finish with a DONE/ERROR sentinel."""
        result_q = queue_mod.Queue()
        stop_event = threading.Event()
        worker = SearchWorker(
            stress_project, "file_", "smart", "", False, result_q, stop_event
        )
        worker.start()
        stop_event.set()
        worker.join(timeout=10)
        assert not worker.is_alive()

        deadline = time.monotonic() + 5
        sentinel = None
        while time.monotonic() < deadline:
            try:
                item = result_q.get(timeout=0.5)
            except queue_mod.Empty:
                break
            if isinstance(item, tuple) and item[0] in ("DONE", "ERROR"):
                sentinel = item
                break
        assert sentinel is not None and sentinel[0] == "DONE"

    def test_backpressure_responds_to_stop_event(self, stress_project):
        """A stuck executor must not block cancellation indefinitely."""
        never_done = concurrent.futures.Future()
        stop_event = threading.Event()

        with patch.object(
            search_mod, "_submit_content_task", lambda *a, **k: never_done
        ):
            gen = search_generator(
                stress_project,
                "target",
                "content",
                "",
                False,
                True,
                stop_event=stop_event,
            )
            done_flag: list[bool] = []

            def consume():
                for _ in gen:
                    pass
                done_flag.append(True)

            t = threading.Thread(target=consume, daemon=True)
            t.start()
            time.sleep(0.5)
            # Simulate user cancellation; with the old indefinite
            # next(as_completed(...)) wait this join would time out.
            stop_event.set()
            t.join(timeout=10)
            assert not t.is_alive(), (
                "search generator did not terminate after stop_event"
            )
            assert done_flag


class TestManualExcludeSubpathPatterns:
    """gitignore-style '/' sub-path patterns must work on Windows too."""

    def test_should_ignore_subpath_pattern(self):
        """A 'docs/*' pattern must match rel paths with '/' separators."""
        rel = pathlib.Path("docs") / "guide.md"
        assert FileUtils.should_ignore("guide.md", rel, ["docs/*"]) is True

    def test_should_ignore_subtree_pattern(self):
        """A 'build/**' pattern must match nested rel paths."""
        rel = pathlib.Path("build") / "out" / "a.obj"
        assert FileUtils.should_ignore("a.obj", rel, ["build/**"]) is True

    def test_walk_filtered_excludes_subpath(self, mock_project):
        """walk_filtered must honor sub-path excludes on every platform."""
        found = [
            str(rel).replace("\\", "/")
            for _full, rel in FileUtils.walk_filtered(
                mock_project, ["src/*"], None, include_dirs=False
            )
        ]
        assert all(not f.startswith("src/") for f in found)
        assert any(f == "config.json" for f in found)


class TestMetadataFallbackContract:
    """get_metadata's failure shape must satisfy downstream consumers."""

    REQUIRED_KEYS = frozenset(
        {
            "name",
            "path",
            "abs_path",
            "type",
            "size",
            "size_fmt",
            "mtime",
            "mtime_fmt",
            "ext",
        }
    )

    def test_fallback_has_full_contract(self, tmp_path):
        """The fallback dict must carry every key of the success branch."""
        ghost = tmp_path / "vanished.txt"
        meta = FileUtils.get_metadata(ghost)
        assert self.REQUIRED_KEYS.issubset(meta.keys())

    def test_ws_search_frame_indexes_path_key(self, tmp_path):
        """The exact access pattern ws_routes uses must not KeyError."""
        ghost = tmp_path / "vanished.txt"
        meta = FileUtils.get_metadata(ghost)
        _ = meta["path"]  # ws_routes.py res_dict["path"]
        _ = meta["size"]
        _ = meta["mtime"]
        _ = meta["ext"]
        _ = meta.get("mtime_fmt", "")
        _ = meta.get("snippet", "")


class TestWsSearchErrorNotSwallowed:
    """A crashing background search must surface an ERROR frame, not DONE."""

    def test_error_frame_delivered(self, project_client, mock_project, monkeypatch):
        """The client must receive ERROR followed by DONE."""
        from routers import ws_routes

        def boom(*args, **kwargs):
            raise RuntimeError("disk exploded")

        monkeypatch.setattr(ws_routes, "search_generator", boom)

        ws_url = f"/ws/search?path={str(mock_project)}&query=main"
        with project_client.websocket_connect(ws_url) as ws:
            first = ws.receive_json()
            assert first.get("status") == "ERROR"
            assert "disk exploded" in first.get("msg", "")
            second = ws.receive_json()
            assert second.get("status") == "DONE"


class TestDuplicateWorkerCancelSentinel:
    """Cancelled DuplicateWorker runs must still enqueue a DONE sentinel."""

    def test_cancelled_run_emits_done(self, mock_project):
        """Immediate cancellation must still produce a terminal sentinel."""
        result_q = queue_mod.Queue()
        stop_event = threading.Event()
        stop_event.set()  # cancel immediately
        worker = DuplicateWorker(mock_project, "", True, result_q, stop_event)
        worker.start()
        worker.join(timeout=10)
        assert not worker.is_alive()

        sentinel = result_q.get(timeout=2)
        # The sentinel contract: cancellation must still deliver a terminal
        # DONE tuple (value depends on whether the scan had completed).
        assert isinstance(sentinel, tuple) and sentinel[0] == "DONE"


# ==============================================================================
# 4. Web auth hardening (P2)
# ==============================================================================


class TestOriginHardening:
    """Origin checks must not trust the client-controlled Host header."""

    def test_spoofed_host_origin_rejected(self, api_client):
        """Origin+Host forged to the same non-local value must be rejected."""
        from fastapi.testclient import TestClient

        client = TestClient(web_app.app, base_url="http://evil.example")
        res = client.get("/api/whoami", headers={"Origin": "http://evil.example"})
        assert res.status_code == 403
        assert res.json()["detail"] == "Origin not allowed"

    def test_local_port_origin_allowed(self, api_client):
        """Any loopback host/port origin stays allowed (dev workflow)."""
        from fastapi.testclient import TestClient

        client = TestClient(web_app.app, base_url="http://localhost:8123")
        res = client.get("/api/whoami", headers={"Origin": "http://localhost:8123"})
        assert res.status_code == 200

    def test_non_ascii_token_header_returns_401_not_500(
        self, api_client, monkeypatch
    ):
        """Non-ASCII tokens must 401, not crash compare_digest -> 500."""
        monkeypatch.setattr(web_app, "API_TOKEN", "secret")
        # Raw latin-1 bytes model a hostile client: httpx refuses str
        # values with non-ASCII, but nothing stops them on the wire.
        # compare_digest(str, str) would raise TypeError -> 500 before
        # the v6.6.0 encode() fix.
        res = api_client.get(
            "/api/whoami", headers={"X-API-Token": "é".encode("latin-1")}
        )
        assert res.status_code == 401


class TestWsAuthCloseCodeDelivery:
    """WS auth failure must deliver close code 4001 to the client."""

    def test_close_code_reaches_client(
        self, project_client, mock_project, monkeypatch
    ):
        """The custom 4001 code must survive past the handshake."""
        from starlette.websockets import WebSocketDisconnect

        monkeypatch.setenv("FCTX_API_TOKEN", "secret_pass")
        ws_url = f"/ws/search?path={str(mock_project)}&query=main&token=wrong"
        with pytest.raises(WebSocketDisconnect) as exc_info, project_client.websocket_connect(
            ws_url
        ) as ws:
            ws.receive_json()
        assert exc_info.value.code == 4001


# ==============================================================================
# 5. Schema bounds & CLI semantics (P3)
# ==============================================================================


class TestSchemaBounds:
    """Request models must reject free-form/bounded violations at 422."""

    def test_generate_rejects_unknown_format(self, project_client, mock_project):
        """"XML" (wrong case) must now be a 422 instead of silent markdown."""
        res = project_client.post(
            "/api/generate",
            json={
                "files": [str(mock_project / "src" / "main.py")],
                "project_path": str(mock_project),
                "export_format": "XML",
            },
        )
        assert res.status_code == 422

    def test_tag_length_bounded(self, project_client, mock_project):
        """Tags over 200 chars must be rejected."""
        res = project_client.post(
            "/api/project/tag",
            json={
                "project_path": str(mock_project),
                "file_path": str(mock_project / "src" / "main.py"),
                "tag": "x" * 201,
                "action": "add",
            },
        )
        assert res.status_code == 422

    def test_batch_rename_count_lower_bound(self, project_client, mock_project):
        """count=0 must be rejected (previously relied on core fallback)."""
        res = project_client.post(
            "/api/fs/batch_rename",
            json={
                "project_path": str(mock_project),
                "paths": [str(mock_project / "src" / "main.py")],
                "pattern": "a",
                "replacement": "b",
                "dry_run": True,
                "count": 0,
            },
        )
        assert res.status_code == 422


class TestSearchQueryBounds:
    """SearchQuery must reject nonsense numeric limits."""

    def test_zero_max_results_rejected(self):
        """max_results=0 would make every search return nothing."""
        import pydantic

        with pytest.raises(pydantic.ValidationError):
            SearchQuery(text="x", max_results=0)

    def test_negative_max_size_rejected(self):
        """Negative max_size_mb previously read the ENTIRE file (read(-1))."""
        import pydantic

        with pytest.raises(pydantic.ValidationError):
            SearchQuery(text="x", max_size_mb=-1)

    def test_zero_max_size_is_valid(self):
        """0 is a legitimate 'skip content reads' limit."""
        assert SearchQuery(text="x", max_size_mb=0).max_size_mb == 0


class TestReadTextSmartNegativeGuard:
    """read_text_smart must treat non-positive limits as 'read nothing'."""

    def test_negative_max_bytes_reads_nothing(self, mock_project):
        """A negative limit must not degenerate into read(-1)."""
        target = mock_project / "src" / "main.py"
        content = FileUtils.read_text_smart(target, max_bytes=-5)
        assert content == ""


class TestCliExitCode:
    """CLI must exit non-zero when no/unknown subcommand is given."""

    def test_no_subcommand_exits_nonzero(self):
        """Shell pipelines must be able to detect the miss via exit code."""
        repo_root = pathlib.Path(__file__).resolve().parent.parent
        proc = subprocess.run(
            [sys.executable, str(repo_root / "fctx.py")],
            capture_output=True,
            timeout=60,
        )
        assert proc.returncode == 2


class TestExtractDirHygiene:
    """A rejected extraction must not leave an empty destination behind."""

    def test_invalid_archive_leaves_no_destination(self, mock_project, tmp_path):
        """FileNotFoundError path must run before mkdir."""
        dst = tmp_path / "never_created"
        with pytest.raises(FileNotFoundError):
            FileOps.extract_archive(
                str(tmp_path / "missing.zip"), str(dst), str(mock_project)
            )
        assert not dst.exists()


class TestMcpPolish:
    """MCP tool polish: format normalization and truncation visibility."""

    @pytest.mark.asyncio
    async def test_fmt_case_insensitive(self, clean_config, mock_project):
        """fmt=" XML " must behave exactly like fmt="xml"."""
        project_path = str(mock_project)
        file_path = str(mock_project / "src" / "main.py")
        await mcp_server.register_workspace(project_path)

        result = await mcp_server.get_file_context(
            project_path, [file_path], fmt=" XML "
        )
        assert "<context>" in result

    @pytest.mark.asyncio
    async def test_search_truncation_notice(self, clean_config, tmp_path):
        """Results cut at the 50-entry cap must say so."""
        base = tmp_path / "many_files"
        base.mkdir()
        for i in range(60):
            (base / f"hitfile_{i:02d}.txt").write_text("x", encoding="utf-8")

        await mcp_server.register_workspace(str(base))
        result = await mcp_server.search_files(str(base), "hitfile_", mode="smart")
        assert "truncated" in result


class TestBatchRenameLiteralReplacement:
    """Simple mode must treat BOTH pattern and replacement as literals."""

    def test_literal_substitution_no_bad_escape(self):
        r"""Escaped replacement must not raise re.error or inject \\n."""
        import re

        from file_cortex_core.gui.batch_rename import build_literal_substitution

        pattern, replacement = build_literal_substitution("old", "new\\name")
        result = re.sub(pattern, replacement, "old.txt")
        assert result == "new\\name.txt"

    def test_literal_substitution_preserves_plain_text(self):
        """Plain ASCII replacements are unaffected by the escaping."""
        import re

        from file_cortex_core.gui.batch_rename import build_literal_substitution

        pattern, replacement = build_literal_substitution("draft", "final")
        assert re.sub(pattern, replacement, "draft_v1.txt") == "final_v1.txt"

    def test_unescaped_control_sequence_would_be_wrong(self):
        """Documents WHY the escaping exists (the old behavior's bug)."""
        import re

        # Without escaping, "\n" in the replacement silently becomes a
        # newline in the filename:
        assert re.sub("draft", "new\\nline", "draft.txt") == "new\nline.txt"


class TestExecuteTimeoutParsing:
    """Malformed FCTX_EXEC_TIMEOUT must fall back to 300s, not crash."""

    def test_invalid_env_falls_back(self, project_client, mock_project, monkeypatch):
        """A garbage env value must not fail every per-path execution."""
        from file_cortex_core import ActionBridge

        monkeypatch.setenv("FCTX_EXEC_TIMEOUT", "not-a-number")
        res = project_client.post(
            "/api/project/tools",
            json={
                "project_path": str(mock_project),
                "tools": {"echo": "python -c pass {path}"},
            },
        )
        assert res.status_code == 200

        fake_proc = MagicMock()
        fake_proc.pid = 4711
        fake_proc.returncode = 0
        fake_proc.communicate.return_value = ("out", "")
        with patch.object(
            ActionBridge, "create_process", staticmethod(lambda *a, **k: fake_proc)
        ):
            exec_res = project_client.post(
                "/api/actions/execute",
                json={
                    "project_path": str(mock_project),
                    "paths": [str(mock_project / "src" / "main.py")],
                    "tool_name": "echo",
                },
            )
        assert exec_res.status_code == 200
        body = exec_res.json()
        assert body["status"] == "ok"
        # The path must have produced a result entry (not a per-path
        # ValueError "failed to start").
        entry = body["results"][0]
        assert "failed to start" not in str(entry.get("error", ""))
        assert entry.get("exit_code") == 0
