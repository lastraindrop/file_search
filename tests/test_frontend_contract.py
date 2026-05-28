"""Frontend structure and contract verification tests."""

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
    js_res = api_client.get("/static/js/main.js")
    css_res = api_client.get("/static/css/style.css")

    assert js_res.status_code == 200
    assert css_res.status_code == 200

    js = js_res.text
    css = css_res.text

    assert "api.openInOs" in js or "/api/fs/open_os" in js
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
    with open("file_search.py", encoding="utf-8", errors="ignore") as f:
        source = f.read()

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

    from routers import fs_routes

    opener = MagicMock()
    monkeypatch.setattr(fs_routes.FileUtils, "open_path_in_os", opener)

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


def test_index_html_uses_collapsible_sections_not_tabs(api_client):
    """Phase 2: Left panel should use collapsible sections, not Bootstrap tabs."""
    html = api_client.get("/").text
    assert "leftTabs" not in html
    assert "panel-tree" not in html
    assert "panel-search" not in html
    assert "panel-fav" not in html
    assert "section-fileTree" in html
    assert "section-searchResults" in html
    assert "section-favorites" in html
    assert "toggleSection" in html


def test_index_html_has_staging_col_md3(api_client):
    """Phase 2: Staging panel should be col-md-3 (widened from col-md-2)."""
    html = api_client.get("/").text
    assert 'class="col-md-3 glass-panel border-start' in html
    assert 'panel-right' in html


def test_main_js_has_toggle_section(api_client):
    """Phase 2: toggleSection should exist in main.js."""
    js = api_client.get("/static/js/main.js").text
    assert "toggleSection" in js
    assert "section-" in js


def test_main_js_has_buildWsUrl(api_client):  # noqa: N802
    """Phase 1: buildWsUrl centralized WS URL construction."""
    js = api_client.get("/static/js/main.js").text
    assert "buildWsUrl" in js


def test_state_js_exports_getFileName(api_client):  # noqa: N802
    """Phase 1: state.js exports getFileName and getFileExt utilities."""
    js = api_client.get("/static/js/state.js").text
    assert "export function getFileName" in js or "export const getFileName" in js
    assert "export function getFileExt" in js or "export const getFileExt" in js
    assert "export function buildWsUrl" in js or "export const buildWsUrl" in js


def test_main_js_no_split_pop_for_filenames(api_client):
    """Phase 1: main.js should use getFileName instead of split/pop for path extraction."""
    js = api_client.get("/static/js/main.js").text
    import re
    matches = re.findall(r'\.split\(/\[', js)
    assert len(matches) == 0, "Found raw .split(/[ in main.js — should use getFileName()"


def test_ui_js_imports_getFileName(api_client):  # noqa: N802
    """Phase 1: ui.js should import getFileName from state.js."""
    js = api_client.get("/static/js/ui.js").text
    assert "getFileName" in js


def test_main_js_no_native_confirm(api_client):
    """Phase 1: main.js should not use native confirm() calls."""
    js = api_client.get("/static/js/main.js").text
    import re
    matches = re.findall(r'(?<![a-zA-Z])confirm\(', js)
    assert len(matches) == 0, "Found native confirm() in main.js — should use actionModal"


def test_main_js_has_debounced_sync(api_client):
    """Phase 4: syncStagingToBackend should use debounce pattern."""
    js = api_client.get("/static/js/main.js").text
    assert "setTimeout" in js
    assert "clearTimeout" in js


def test_index_html_has_sri_integrity(api_client):
    """Phase 3: CDN resources should have integrity hashes."""
    html = api_client.get("/").text
    assert "integrity=" in html
    assert "sha384-" in html


def test_index_html_pinned_cdn_versions(api_client):
    """Phase 3: marked and mermaid should be pinned to specific versions."""
    html = api_client.get("/").text
    assert "marked@" in html
    assert "mermaid@" in html


def test_main_js_has_tag_management(api_client):
    """Phase 3: main.js should have addTag and removeTag methods."""
    js = api_client.get("/static/js/main.js").text
    assert "addTag" in js
    assert "removeTag" in js


def test_main_js_has_create_file(api_client):
    """Phase 3: main.js should have createFile method."""
    js = api_client.get("/static/js/main.js").text
    assert "createFile" in js


def test_index_html_has_new_file_button(api_client):
    """Phase 3: Files section header should have a +New button."""
    html = api_client.get("/").text
    assert "App.createFile" in html


def test_index_html_keyboard_help_updated(api_client):
    """Phase 2: Help modal should say Toggle Sections, not Switch Tabs."""
    html = api_client.get("/").text
    assert "Toggle Sections" in html
    assert "Switch Tabs" not in html


def test_css_has_section_styles(api_client):
    """Phase 2: CSS should have collapsible section styles."""
    css = api_client.get("/static/css/style.css").text
    assert "section-header" in css
    assert "section-toggle" in css
    assert "cursor-pointer" in css


class TestFrontendBugFixes:
    """Verify frontend bug fixes applied correctly in v6.5.0."""

    def test_bulk_actions_not_force_hidden(self, api_client):
        """FrontFix-1: bulkActions div should NOT have `!important` on display."""
        html = api_client.get("/").text
        assert 'display:none !important' not in html

    def test_no_global_tree_node_query(self, api_client):
        """FrontFix-4: ui.js should scope tree-node query to container, not document."""
        js = api_client.get("/static/js/ui.js").text
        assert "document.querySelectorAll('.tree-node')" not in js
        assert "querySelectorAll('.tree-node')" in js  # scoped version OK

    def test_stage_all_uses_fixed_mode(self, api_client):
        """FrontFix-2: stageAll should pass 'files' mode, not search mode."""
        js = api_client.get("/static/js/main.js").text
        assert "api.stageAll(App.state.projectPath, 'files', true)" in js

    def test_context_menu_overflow_guard(self, api_client):
        """FrontFix-6: showContextMenu should have viewport boundary checks."""
        js = api_client.get("/static/js/main.js").text
        assert "window.innerWidth" in js
        assert "window.innerHeight" in js

    def test_search_results_cleared_on_new_search(self, api_client):
        """FrontFix-3: startSearch should clear left panel search results."""
        js = api_client.get("/static/js/main.js").text
        assert "leftList.innerHTML = ''" in js

    def test_create_key_value_row_sanitized(self, api_client):
        """FrontFix-7: _createKeyValueRow should sanitize key for DOM id."""
        js = api_client.get("/static/js/main.js").text
        assert "replace(/[^a-zA-Z0-9_-]/g" in js

    def test_note_overlay_positioning(self, api_client):
        """FrontFix-6: noteOverlay should not have hardcoded absolute positioning."""
        html = api_client.get("/").text
        assert 'start-50 translate-middle-x' in html

    def test_bulk_actions_uses_normal_display(self, api_client):
        """FrontFix-1: updateBulkUI should use normal style.display, not setProperty important."""
        js = api_client.get("/static/js/main.js").text
        assert "style.setProperty('display'" not in js
