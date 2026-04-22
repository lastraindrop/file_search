import pytest
import os
from file_cortex_core import ContextFormatter, PathValidator

def test_xml_export_with_blueprint(mock_project):
    """Verify that XML export includes the <blueprint> tag when enabled."""
    root = str(mock_project)
    files = [str(mock_project / "src" / "main.py")]
    
    # 1. Test with blueprint (default)
    xml_with = ContextFormatter.to_xml(files, root_dir=root, include_blueprint=True)
    assert "<blueprint>" in xml_with
    assert "Project: mock_project" in xml_with
    assert "</blueprint>" in xml_with
    assert "<context>" in xml_with
    
    # 2. Test without blueprint
    xml_without = ContextFormatter.to_xml(files, root_dir=root, include_blueprint=False)
    assert "<blueprint>" not in xml_without
    assert "<context>" in xml_without

def test_websocket_auth_failure(project_client, mock_project, monkeypatch):
    """Verify that WebSocket connection fails with invalid token."""
    # Set a required token
    monkeypatch.setenv("FCTX_API_TOKEN", "secret_pass")
    
    # Try to connect without token or with wrong token
    # FastAPI/TestClient WebSocket auth is usually checked via query params in our implementation
    
    with project_client.websocket_connect(f"/ws/search?path={str(mock_project)}&query=main&token=wrong") as ws:
        data = ws.receive_json()
        assert data["status"] == "ERROR"
        assert "Unauthorized" in data["msg"]

def test_websocket_auth_success(project_client, mock_project, monkeypatch):
    """Verify that WebSocket connection succeeds with valid token."""
    token = "secret_pass"
    monkeypatch.setenv("FCTX_API_TOKEN", token)
    
    with project_client.websocket_connect(f"/ws/search?path={str(mock_project)}&query=main&token={token}") as ws:
        data = ws.receive_json()
        # Should start sending results or DONE, not ERROR
        assert data.get("status") != "ERROR"

def test_api_generate_blueprint_param(project_client, mock_project):
    """Verify the include_blueprint parameter in the /api/generate endpoint."""
    root = str(mock_project)
    f1 = str(mock_project / "src" / "main.py")
    
    # Test XML with blueprint
    res = project_client.post("/api/generate", json={
        "files": [f1],
        "project_path": root,
        "export_format": "xml",
        "include_blueprint": True
    })
    assert "<blueprint>" in res.json()["content"]
    
    # Test XML without blueprint
    res2 = project_client.post("/api/generate", json={
        "files": [f1],
        "project_path": root,
        "export_format": "xml",
        "include_blueprint": False
    })
    assert "<blueprint>" not in res2.json()["content"]

def test_is_safe_with_traversal_variations():
    """Rigorously test is_safe with complex traversal strings."""
    root = "C:/User/Project" if os.name == 'nt' else "/tmp/project"
    
    # Valid relative
    assert PathValidator.is_safe("src/main.py", root) is True
    # Traversal out
    assert PathValidator.is_safe("../evil.txt", root) is False
    # Complex but safe (staying inside)
    assert PathValidator.is_safe("src/../src/main.py", root) is True
    # UNC (always unsafe)
    assert PathValidator.is_safe("//server/share/file.txt", root) is False

def test_format_size_edge_cases():
    """Verify FormatUtils.format_size handles large and small values."""
    from file_cortex_core import FormatUtils
    assert FormatUtils.format_size(1024*1024*1024*2) == "2.0 GB"
    assert FormatUtils.format_size(1024*500) == "500.0 KB"
    assert FormatUtils.format_size(-1) == "0 B"

def test_noise_reducer_minified_js():
    """Verify NoiseReducer handles minified JS correctly."""
    from file_cortex_core import NoiseReducer
    minified = "function a(b){console.log(b);}" * 100 # Long line
    cleaned = NoiseReducer.clean(minified, max_line_length=50)
    assert "skipped by NoiseReducer" in cleaned
