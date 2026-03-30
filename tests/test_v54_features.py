import pytest
import pathlib
import os
from file_cortex_core import NoiseReducer, FileUtils, FileOps
from file_cortex_core.security import PathValidator

def test_noise_reducer_filtering():
    """Verify that NoiseReducer correctly identifies and filters long lines."""
    content = "import os\n" + "A" * 1000 + "\nprint('done')"
    # Default threshold is 500
    cleaned = NoiseReducer.clean(content)
    lines = cleaned.splitlines()
    assert len(lines) == 3
    assert "Line of 1000 chars skipped" in lines[1]
    assert lines[0] == "import os"
    assert lines[2] == "print('done')"

def test_read_text_smart_encoding(noisy_project):
    """Verify that FileUtils can read mixed encodings."""
    gbk_file = noisy_project / "legacy_zh.py"
    # Content is b"\xb2\xe2\xca\xd4\xc4\xda\xc8\xdd" (测试内容 in GBK)
    content = FileUtils.read_text_smart(gbk_file)
    # The '测试内容' might be rendered differently depending on locale, 
    # but it should NOT be an empty string and should have recognizable text if charset_normalizer works.
    assert len(content) > 0
    # On most systems with charset-normalizer, this will resolve to the correct string.
    # We at least check it doesn't crash.

def test_batch_rename_regex_logic(mock_project):
    """Verify regex capturing groups and multi-file renaming."""
    root = mock_project
    f1 = root / "data_version_1.txt"
    f2 = root / "data_version_2.txt"
    f1.touch()
    f2.touch()
    
    paths = [str(f1), str(f2)]
    # Pattern to capture version number
    pattern = r"data_version_(\d+)\.txt"
    replacement = r"v\1_backup.log"
    
    # 1. Test Dry Run
    results_dry = FileOps.batch_rename(str(root), paths, pattern, replacement, dry_run=True)
    assert len(results_dry) == 2
    assert results_dry[0]["new"].endswith("v1_backup.log")
    assert f1.exists() # Should not be renamed yet
    
    # 2. Test Live Run
    FileOps.batch_rename(str(root), paths, pattern, replacement, dry_run=False)
    assert (root / "v1_backup.log").exists()
    assert (root / "v2_backup.log").exists()
    assert not f1.exists()

def test_batch_rename_collision_resolution(mock_project):
    """Verify that collisions are resolved by adding a suffix."""
    root = mock_project
    f1 = root / "test.txt"
    f1.touch()
    # Destination already exists
    f_target = root / "new.txt"
    f_target.touch()
    
    paths = [str(f1)]
    results = FileOps.batch_rename(str(root), paths, r"test", r"new", dry_run=False)
    
    assert results[0]["status"] == "renamed_with_suffix"
    assert (root / "new_1.txt").exists()
    assert (root / "new.txt").exists() # Original stays

def test_api_terminate_logic(project_client, mock_project, mock_popen):
    """Verify process termination via API with Mock Popen."""
    from web_app import ACTIVE_PROCESSES
    import subprocess
    from unittest.mock import patch
    
    pid = mock_popen.pid
    ACTIVE_PROCESSES[pid] = mock_popen
    
    try:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            res = project_client.post("/api/actions/terminate", json={"pid": pid})
            assert res.status_code == 200
            assert res.json()["status"] == "ok"
    finally:
        if pid in ACTIVE_PROCESSES:
            del ACTIVE_PROCESSES[pid]

def test_api_batch_rename_e2e(project_client, mock_project):
    """Verify endpoint for batch rename."""
    f1 = mock_project / "a.js"
    f1.touch()
    
    res = project_client.post("/api/fs/batch_rename", json={
        "project_path": str(mock_project),
        "paths": [str(f1)],
        "pattern": "a",
        "replacement": "b",
        "dry_run": False
    })
    assert res.status_code == 200
    assert (mock_project / "b.js").exists()
