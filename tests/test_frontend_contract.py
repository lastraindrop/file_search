from unittest.mock import MagicMock

import pytest


def test_index_contains_updated_frontend_contract(api_client):
    """Main page should expose the latest UI controls and shared action modal."""
    res = api_client.get("/")
    assert res.status_code == 200
    html = res.text

    required_ids = [
        "workspaceSummaryBar",
        "summaryProjectName",
        "summarySearchState",
        "searchIncludeDirs",
        "searchCaseSensitive",
        "searchInverse",
        "btnOpenExternal",
        "set-token-threshold",
        "set-token-ratio",
        "actionModal",
        "actionModalConfirm",
    ]
    for required_id in required_ids:
        assert required_id in html


def test_static_assets_reflect_current_frontend_architecture(api_client):
    """Static assets should target the new OS-open endpoint and search flags."""
    js_res = api_client.get("/static/js/app.js")
    css_res = api_client.get("/static/css/style.css")

    assert js_res.status_code == 200
    assert css_res.status_code == 200

    js = js_res.text
    css = css_res.text

    assert "/api/fs/open_os" in js
    assert "searchIncludeDirs" in js
    assert "searchCaseSensitive" in js
    assert "searchInverse" in js
    assert "loadTreeChildren" in js
    assert "initialExpand: true" in js
    assert "summary-bar" in css
    assert "search-option-grid" in css
    assert "tree-toggle" in css


def test_desktop_gui_avoids_hardcoded_image_processor_menu():
    """Desktop GUI should expose generic custom-tool actions, not fixed image tools."""
    source = open("file_search.py", encoding="utf-8", errors="ignore").read()

    # Avoid checking localized Chinese strings which are prone to encoding issues in tests
    assert "image_splitter" not in source
    assert "ctx_send_to_image_splitter" not in source
    assert "context_tool_menu" in source
    assert "ctx_execute_custom_tool" in source
    # Check for logic methods instead of UI text
    assert "ctx_add_to_staging" in source
    assert "FileCortexApp" in source

    assert "ctx_add_to_staging" in source


def test_api_open_os_uses_shell_open(project_client, mock_project, monkeypatch):
    """Open-in-OS endpoint should call the shell opener for authorized paths."""
    target = mock_project / "src" / "main.py"

    import routers.http_routes as http_routes

    opener = MagicMock()
    monkeypatch.setattr(http_routes.FileUtils, "open_path_in_os", opener)

    res = project_client.post(
        "/api/fs/open_os",
        json={
            "project_path": str(mock_project),
            "path": str(target),
        },
    )
    assert res.status_code == 200
    opener.assert_called_once()


@pytest.mark.parametrize(
    ("query", "mode", "case_sensitive", "include_dirs", "expected_fragment"),
    [
        ("src", "exact", False, True, "Folder"),
        ("MAIN", "exact", False, False, "main.py"),
    ],
)
def test_websocket_search_parameter_matrix(
    project_client,
    mock_project,
    query,
    mode,
    case_sensitive,
    include_dirs,
    expected_fragment,
):
    """WebSocket search should honor current frontend search parameters."""
    with project_client.websocket_connect(
        "/ws/search"
        f"?path={str(mock_project)}"
        f"&query={query}"
        f"&mode={mode}"
        f"&case_sensitive={str(case_sensitive).lower()}"
        f"&include_dirs={str(include_dirs).lower()}"
    ) as ws:
        payloads = []
        while True:
            data = ws.receive_json()
            if data.get("status") == "DONE":
                break
            payloads.append(str(data))

    combined = "\n".join(payloads)
    assert expected_fragment in combined


def test_websocket_search_case_sensitive_no_match(project_client, mock_project):
    """Case-sensitive search should not match when only case-insensitive text exists."""
    with project_client.websocket_connect(
        "/ws/search"
        f"?path={str(mock_project)}"
        "&query=MAIN"
        "&mode=exact"
        "&case_sensitive=true"
    ) as ws:
        payloads = []
        while True:
            data = ws.receive_json()
            if data.get("status") == "DONE":
                break
            payloads.append(data)

    assert payloads == []
