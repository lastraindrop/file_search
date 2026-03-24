import pytest
import pathlib
import tempfile
import shutil
import os

@pytest.fixture
def mock_project():
    """Creates a temporary project directory with various files."""
    temp_dir = tempfile.mkdtemp(prefix="ai_workbench_mock_")
    base = pathlib.Path(temp_dir)
    
    # Standard files
    (base / "src").mkdir()
    (base / "src" / "main.py").write_text("print('hello')", encoding="utf-8")
    (base / "src" / "utils.js").write_text("console.log('test'); print('done')", encoding="utf-8")
    
    # New files for permutations
    (base / "config.json").write_text("{}", encoding="utf-8")
    (base / "data.bin").write_bytes(b"\x00\xff\x00\xffhello")
    
    # Binary file
    (base / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")
    
    # Gitignore and ignored files
    (base / ".gitignore").write_text("*.log\nnode_modules/", encoding="utf-8")
    (base / "error.log").write_text("some error", encoding="utf-8")
    (base / "node_modules").mkdir()
    (base / "node_modules" / "package.json").write_text("{}", encoding="utf-8")
    
    yield base
    
    shutil.rmtree(temp_dir)

@pytest.fixture
def stress_project():
    """Creates a temporary project with multiple directories and 100+ files."""
    temp_dir = tempfile.mkdtemp(prefix="ai_workbench_stress_")
    base = pathlib.Path(temp_dir)
    
    # Create 10 directories
    for i in range(10):
        d = base / f"dir_{i}"
        d.mkdir()
        # Create 10 files in each directory
        for j in range(10):
            f = d / f"file_{j}.txt"
            f.write_text(f"Content in file {i}-{j} with keyword_target_{j}", encoding="utf-8")
            
    # Add some binary files and ignored files
    (base / "ignored.log").write_text("should be ignored", encoding="utf-8")
    (base / ".gitignore").write_text("*.log", encoding="utf-8")
    
    yield base
    shutil.rmtree(temp_dir)
