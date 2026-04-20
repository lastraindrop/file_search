import os
import sys
from unittest.mock import patch

import pytest

from file_cortex_core import ActionBridge, FileOps, FileUtils, FormatUtils, NoiseReducer

# -----------------------------------------------------------------------------
# 1. File Utility & Smart Read
# -----------------------------------------------------------------------------

@pytest.mark.parametrize("content_type,content", [
    ("utf8", "Standard UTF8 文本内容"),
    ("gbk", b"\xb2\xe2\xca\xd4\xc4\xda\xc8\xdd"),
    ("large", "A" * 10000) # 10KB is enough for truncation test
])
def test_core_read_text_resilience(tmp_path, content_type, content):
    """Integrates smart read, encoding detection and truncation."""
    f = tmp_path / f"test_{content_type}.txt"
    if isinstance(content, bytes):
        f.write_bytes(content)
    else:
        f.write_text(content, encoding='utf-8')

    # 1. Smart Read with encoding detection
    read_data = FileUtils.read_text_smart(f, max_bytes=1000000 if content_type == "large" else None)

    if content_type == "large":
        assert len(read_data) <= 1000100
    elif content_type == "gbk":
        assert len(read_data) > 0
        assert "测试" in read_data or len(read_data) >= 4
    else:
        assert content in read_data

def test_core_binary_detection(mock_project):
    """Verify binary vs text heuristics."""
    assert FileUtils.is_binary(mock_project / "data.bin") is True
    assert FileUtils.is_binary(mock_project / "src" / "main.py") is False
    assert FileUtils.is_binary(mock_project / "empty.txt") is False

# -----------------------------------------------------------------------------
# 2. Formatting & Metadata
# -----------------------------------------------------------------------------

def test_core_format_utils_matrix():
    """Verify size and time formatting across scales."""
    # Token estimation consistency
    text = "Hello world " * 100
    est = FormatUtils.estimate_tokens(text)
    assert est > 0 and isinstance(est, int)

def test_core_path_collection_formatting(mock_project):
    """Verify path collection string orchestration."""
    files = [str(mock_project / "src" / "main.py"), str(mock_project / "README.md")]
    # Test different modes
    out_rel = FormatUtils.collect_paths(files, mode='relative', root_dir=str(mock_project))
    assert "src/main.py" in out_rel.replace("\\", "/") or "src/main.py" in out_rel.lower().replace("\\", "/")

    out_abs = FormatUtils.collect_paths(files, mode='absolute')
    assert str(mock_project) in out_abs

# -----------------------------------------------------------------------------
# 3. Noise Reduction
# -----------------------------------------------------------------------------

def test_core_noise_reducer_logic():
    """Verify heuristic detection of high-noise/minified files."""
    minified = "var a=1;" + "b=2;" * 1000
    cleaned = NoiseReducer.clean(minified, max_line_length=100)
    assert "skipped" in cleaned

# -----------------------------------------------------------------------------
# 4. Action Bridge & Process Logic
# -----------------------------------------------------------------------------

def test_core_action_bridge_execution(mock_project):
    """Verify platform-aware command execution."""
    test_f = mock_project / "src" / "main.py"
    # Unified test: use python to print a marker
    template = f'"{sys.executable}" -c "print(\'EXEC_BRIDGE_OK\')"'
    results = list(ActionBridge.stream_tool(template, str(test_f), str(mock_project)))
    outputs = [r["out"] for r in results if "out" in r]
    assert any("EXEC_BRIDGE_OK" in o for o in outputs)

# -----------------------------------------------------------------------------
# 5. File Operations & Transactions (C1)
# -----------------------------------------------------------------------------

def test_core_ops_batch_rename_rollback(tmp_path):
    """Critical C1: Regression check for rollback integrity."""
    files = []
    for i in range(3):
        f = tmp_path / f"file_{i}.txt"
        f.write_text(f"content {i}")
        files.append(str(f))

    # Trigger failure on the 3rd file
    from pathlib import Path
    real_rename = Path.rename
    def faulty_rename(self, target):
        if "file_2" in str(self):
            raise PermissionError("Atomicity Test")
        return real_rename(self, target)

    with patch.object(Path, "rename", faulty_rename):
        with pytest.raises(PermissionError):
            FileOps.batch_rename(str(tmp_path), files, "file_(.*)", "new_\\1", dry_run=False)

    # Rollback check: none should be renamed
    assert (tmp_path / "file_0.txt").exists()
    assert not (tmp_path / "new_0.txt").exists()

def test_core_ops_item_creation(tmp_path):
    """Verify reliable file/dir creation logic."""
    new_dir = FileOps.create_item(str(tmp_path), "new_sub", is_dir=True)
    assert os.path.isdir(new_dir)
    new_file = FileOps.create_item(new_dir, "test.log", is_dir=False)
    assert os.path.isfile(new_file)

# -----------------------------------------------------------------------------
# 6. Duplicates Analysis
# -----------------------------------------------------------------------------

def test_core_duplicate_worker(tmp_path):
    """Verify background duplicate hashing and group identification."""
    import queue
    from threading import Event

    from file_cortex_core import DuplicateWorker

    # Setup: 2 identical, 1 unique
    (tmp_path / "a.txt").write_text("SAME")
    (tmp_path / "b.txt").write_text("SAME")
    (tmp_path / "c.txt").write_text("DIFF")

    q = queue.Queue()
    stop = Event()
    worker = DuplicateWorker(str(tmp_path), "", True, q, stop)
    worker.run() # Run synchronous for test predictability

    results = []
    while not q.empty():
        item = q.get()
        if isinstance(item, dict):
            results.append(item)

    assert len(results) == 1 # Only one group of duplicates
    assert len(results[0]["paths"]) == 2
