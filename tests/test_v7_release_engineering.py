"""v7.0 release-engineering and review-fix regression tests.

Covers:
- FCTX_CONFIG_DIR relocation for containerized deployments.
- /healthz unauthenticated liveness endpoint.
- Nested .gitignore chain (parent rules + child re-include).
- CLI relative export cannot escape the project root.
- Progress endpoints use validated Pydantic schemas.
- DuplicateWorker emits a DONE sentinel after ERROR.
- Frontend source contracts for the v7.0 fixes.
"""

from __future__ import annotations

import pathlib
import queue
import threading
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from file_cortex_core import DataManager, FileUtils, PathValidator, search_generator
from web_app import app

# ---------------------------------------------------------------------------
# FCTX_CONFIG_DIR
# ---------------------------------------------------------------------------


def test_config_dir_env_override(tmp_path, monkeypatch):
    """get_app_dir() honors FCTX_CONFIG_DIR over the home default."""
    from file_cortex_core.config import get_app_dir

    target = tmp_path / "relocated-config"
    monkeypatch.setenv("FCTX_CONFIG_DIR", str(target))
    assert get_app_dir() == target
    assert target.is_dir()


def test_config_dir_env_unset_falls_back_to_home(monkeypatch):
    """Without the env var the legacy ~/.filecortex location is preserved."""
    from file_cortex_core.config import get_app_dir

    monkeypatch.delenv("FCTX_CONFIG_DIR", raising=False)
    assert get_app_dir() == pathlib.Path.home() / ".filecortex"


def test_config_file_relocates_with_env(tmp_path, monkeypatch):
    """A fresh DataManager writes into the relocated directory."""
    from file_cortex_core import config as config_mod

    target = tmp_path / "cfg"
    monkeypatch.setenv("FCTX_CONFIG_DIR", str(target))
    monkeypatch.setattr(config_mod, "_CONFIG_FILE", None)
    relocated = config_mod.get_app_dir() / "config.json"
    DataManager.reset()
    with (
        patch("file_cortex_core.config._CONFIG_FILE", relocated),
        patch.object(config_mod, "_get_config_file", lambda: relocated),
    ):
        dm = DataManager.create()
        dm.add_to_recent(str(tmp_path))
    assert (target / "config.json").exists()
    DataManager.reset()


# ---------------------------------------------------------------------------
# /healthz
# ---------------------------------------------------------------------------


def test_healthz_is_unauthenticated(tmp_path):
    """The liveness probe must answer 200 without an API token."""
    with (
        patch("file_cortex_core.config._CONFIG_FILE", tmp_path / "c.json"),
        patch("web_app.API_TOKEN", "secret-token"),
    ):
        DataManager.reset()
        client = TestClient(app)
        res = client.get("/healthz")
        assert res.status_code == 200
        assert res.json()["status"] == "ok"


def test_api_token_still_enforced(tmp_path):
    """Setting a token must still gate /api/ endpoints (whoami as probe)."""
    with (
        patch("file_cortex_core.config._CONFIG_FILE", tmp_path / "c.json"),
        patch("web_app.API_TOKEN", "secret-token"),
    ):
        DataManager.reset()
        client = TestClient(app)
        assert client.get("/api/whoami").status_code == 401
        ok = client.get("/api/whoami", headers={"X-API-Token": "secret-token"})
        assert ok.status_code == 200


# ---------------------------------------------------------------------------
# Nested .gitignore
# ---------------------------------------------------------------------------


@pytest.fixture
def nested_ignore_project(tmp_path):
    """Parent excludes *.log; child re-includes error.log and adds *.tmp."""
    root = tmp_path / "nested"
    (root / "sub").mkdir(parents=True)
    (root / ".gitignore").write_text("*.log\nbuild/\n", encoding="utf-8")
    (root / "sub" / ".gitignore").write_text("!error.log\n*.tmp\n", encoding="utf-8")
    (root / "a.log").write_text("x", encoding="utf-8")
    (root / "keep.txt").write_text("x", encoding="utf-8")
    (root / "sub" / "error.log").write_text("x", encoding="utf-8")
    (root / "sub" / "b.log").write_text("x", encoding="utf-8")
    (root / "sub" / "x.tmp").write_text("x", encoding="utf-8")
    (root / "build").mkdir()
    (root / "build" / "out.txt").write_text("x", encoding="utf-8")
    return root


def test_nested_gitignore_child_reinclude(nested_ignore_project):
    """A child '!error.log' overrides the parent '*.log' (git semantics)."""
    FileUtils.clear_cache()
    root = nested_ignore_project
    spec = FileUtils.get_gitignore_spec(root)
    found = {str(rel).replace("\\", "/") for _, rel in FileUtils.walk_filtered(root, [], spec)}
    assert "keep.txt" in found
    assert "sub/error.log" in found
    assert "a.log" not in found
    assert "sub/b.log" not in found
    assert "sub/x.tmp" not in found
    assert "build/out.txt" not in found


def test_nested_gitignore_search_parity(nested_ignore_project):
    """search_generator must not return files hidden by nested rules."""
    FileUtils.clear_cache()
    root = nested_ignore_project
    # inverse mode with an empty query lists every non-ignored path.
    results = list(
        search_generator(
            root, "", "smart", "", include_dirs=False, use_gitignore=True, is_inverse=True
        )
    )
    paths = {r["path"].replace("\\", "/") for r in results}
    assert any(p.endswith("keep.txt") for p in paths)
    assert any(p.endswith("sub/error.log") for p in paths)
    assert not any(p.endswith("a.log") for p in paths)
    assert not any(p.endswith("sub/b.log") for p in paths)


def test_nested_gitignore_flatten_paths(nested_ignore_project):
    """flatten_paths (export) honors the nested chain too."""
    FileUtils.clear_cache()
    root = nested_ignore_project
    flat = FileUtils.flatten_paths([str(root)], str(root), [], True)
    names = {str(pathlib.Path(p).relative_to(root)).replace("\\", "/") for p in flat}
    assert "sub/error.log" in names
    assert "sub/b.log" not in names
    assert "sub/x.tmp" not in names


# ---------------------------------------------------------------------------
# CLI relative export sandbox
# ---------------------------------------------------------------------------


def test_cli_relative_export_cannot_escape(tmp_path, monkeypatch):
    """Fctx export -o ../x must be rejected (relative paths stay inside)."""
    import fctx as cli

    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "a.txt").write_text("data", encoding="utf-8")

    from unittest.mock import MagicMock

    dm = MagicMock()
    dm.resolve_project_root.return_value = PathValidator.norm_path(proj)
    dm.get_project_data.return_value = {"staging_list": [str(proj / "a.txt")]}

    args = MagicMock()
    args.project = str(proj)
    args.output = "../escaped.md"
    args.format = "markdown"
    args.noise_reducer = False

    ok = cli.cmd_export(args, dm)
    assert ok is False
    assert not (tmp_path / "escaped.md").exists()


def test_cli_absolute_export_allowed(tmp_path):
    """An explicitly absolute --output remains a user choice."""
    from unittest.mock import MagicMock

    import fctx as cli

    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "a.txt").write_text("data", encoding="utf-8")
    out = tmp_path / "explicit.md"

    dm = MagicMock()
    dm.resolve_project_root.return_value = PathValidator.norm_path(proj)
    dm.get_project_data.return_value = {"staging_list": [str(proj / "a.txt")]}

    args = MagicMock()
    args.project = str(proj)
    args.output = str(out)
    args.format = "markdown"
    args.noise_reducer = False

    assert cli.cmd_export(args, dm) is True
    assert out.exists()


# ---------------------------------------------------------------------------
# Progress endpoint schemas
# ---------------------------------------------------------------------------


def test_progress_endpoints_validate_payload(tmp_path):
    """Unknown/malformed bodies are rejected with 422, not 500."""
    with patch("file_cortex_core.config._CONFIG_FILE", tmp_path / "c.json"):
        DataManager.reset()
        client = TestClient(app)
        bad = client.post("/api/fs/progress", json={"task_id": 123})
        assert bad.status_code == 422
        good_new = client.post("/api/fs/progress/new", json={"total": 3})
        assert good_new.status_code == 200
        task_id = good_new.json()["task_id"]
        good = client.post("/api/fs/progress", json={"task_id": task_id})
        assert good.status_code == 200
        assert good.json()["total"] == 3


# ---------------------------------------------------------------------------
# DuplicateWorker sentinel contract
# ---------------------------------------------------------------------------


def test_duplicate_worker_error_emits_done(tmp_path):
    """A crashing scan must leave both ERROR and DONE in the queue."""
    from file_cortex_core.duplicate import DuplicateWorker

    q: queue.Queue = queue.Queue()
    worker = DuplicateWorker(tmp_path, "", False, q, threading.Event())

    def _boom(*_args, **_kwargs):
        raise RuntimeError("scan exploded")

    with patch.object(DuplicateWorker, "_get_hash", _boom), patch(
        "file_cortex_core.duplicate.FileUtils.walk_filtered",
        side_effect=RuntimeError("scan exploded"),
    ):
        worker.run()

    items = []
    while not q.empty():
        items.append(q.get_nowait())
    kinds = [i[0] if isinstance(i, tuple) else "result" for i in items]
    assert "ERROR" in kinds
    assert kinds[-1] == "DONE"


# ---------------------------------------------------------------------------
# Frontend source contracts (v7.0 fixes)
# ---------------------------------------------------------------------------


def _read(rel: str) -> str:
    root = pathlib.Path(__file__).resolve().parent.parent
    return (root / rel).read_text(encoding="utf-8")


def test_openproject_stops_search_and_flushes_staging():
    """OpenProject must invalidate in-flight searches and flush staging."""
    js = _read("static/js/main.js")
    assert "stopSearchInFlight" in js
    open_idx = js.index("openProject: async")
    body = js[open_idx : open_idx + 1500]
    assert "stopSearchInFlight()" in body
    assert "syncStagingToBackend.flushNow()" in body


def test_startsearch_silent_debounce():
    """Debounced input must not warn about an empty query."""
    js = _read("static/js/main.js")
    assert "App.startSearch(true)" in js
    assert "silent === true" in js


def test_section_visibility_uses_correct_element():
    """Select-all visibility must check the section container, not the list."""
    js = _read("static/js/main.js")
    assert "searchList.style.display !== 'none'" not in js
    assert "searchSection.style.display !== 'none'" in js


def test_fetch_has_timeout():
    """api.js must arm an AbortController timeout."""
    js = _read("static/js/api.js")
    assert "AbortController" in js
    assert "timeoutMs" in js


def test_modal_get_or_create_instance():
    """Bootstrap modals are obtained, not re-instantiated per call."""
    assert "new bootstrap.Modal(" not in _read("static/js/main.js")
    assert "new bootstrap.Modal(" not in _read("static/js/ui.js")
    assert "bootstrap.Modal.getOrCreateInstance(" in _read("static/js/main.js")


def test_virtual_list_resize_observer():
    """Panel resizes must trigger a re-render (stale visible slice fix)."""
    js = _read("static/js/virtual-list.js")
    assert "ResizeObserver" in js
    assert "observer.disconnect()" in js
