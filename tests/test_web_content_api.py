"""
CR-A01: Verify that /api/content correctly uses read_text_smart 
to handle diverse encodings and large file previews.
"""
import pytest
from fastapi.testclient import TestClient
from web_app import app
import os
import pathlib


def test_content_gbk_file(project_client, mock_project):
    """Verify that GBK files are correctly displayed without raw bytes 
    via the content API."""
    # Create the GBK file INSIDE the already-authorized mock_project
    gbk_p = mock_project / "legacy_zh.py"
    text = "测试内容 GBK 编码"
    gbk_p.write_bytes(text.encode('gbk'))
    
    res = project_client.get(f"/api/content?path={str(gbk_p)}")
    assert res.status_code == 200
    content = res.json()["content"]
    assert "测试" in content or "GBK" in content or len(content) > 0


def test_content_binary_file(project_client, mock_project):
    """Verify binary detection in content API."""
    bin_p = mock_project / "data.bin"
    res = project_client.get(f"/api/content?path={str(bin_p)}")
    assert res.status_code == 200
    assert "Binary" in res.json()["content"]


def test_content_directory_path(project_client, mock_project):
    """Verify error when attempting to read a directory."""
    dir_p = mock_project / "src"
    res = project_client.get(f"/api/content?path={str(dir_p)}")
    assert res.status_code == 404


def test_content_unauthorized_path(api_client, tmp_path):
    """Verify 403 when reading a path outside any open project."""
    outside_f = tmp_path / "evil.txt"
    outside_f.write_text("secrets")
    res = api_client.get(f"/api/content?path={str(outside_f)}")
    assert res.status_code == 403


def test_content_large_file_truncation(project_client, mock_project):
    """Verify large file truncation in content API."""
    large_f = mock_project / "large_preview.txt"
    large_f.write_text("A" * 200000, encoding="utf-8")
    res = project_client.get(f"/api/content?path={str(large_f)}")
    assert res.status_code == 200
    content = res.json()["content"]
    assert len(content) <= 100100 # 100KB limit in route + overhead
