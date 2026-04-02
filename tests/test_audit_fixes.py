import pytest
import pathlib
import os
import stat
import shutil
from file_cortex_core import search_generator, PathValidator, ActionBridge, FileOps, FileUtils

# CR-21/22 Fix Style: Use local sandbox to avoid Windows permissions issues with tmp_path
AUDIT_TEMP = pathlib.Path("tests/tmp_tests/audit_fix_sandbox")

@pytest.fixture(autouse=True)
def setup_teardown():
    if AUDIT_TEMP.exists():
        shutil.rmtree(AUDIT_TEMP, ignore_errors=True)
    AUDIT_TEMP.mkdir(parents=True, exist_ok=True)
    yield
    if AUDIT_TEMP.exists():
        shutil.rmtree(AUDIT_TEMP, ignore_errors=True)

def test_cr02_regex_no_duplication():
    """CR-02: Ensure regex mode doesn't produce duplicate results when matching both name and content."""
    root = AUDIT_TEMP / "regex_test"
    root.mkdir()
    f1 = root / "match.py"
    f1.write_text("match this")
    
    results = list(search_generator(str(root), "match", "regex", ""))
    assert len(results) == 1

def test_cr05_dot_search_with_tags():
    """CR-05: Ensure '.' search text doesn't short-circuit tag matching."""
    root = AUDIT_TEMP / "tag_test"
    root.mkdir()
    f1 = root / "file1.txt"; f1.write_text("hello")
    
    # query '.' should return 0 results if no tags are present
    res_empty = list(search_generator(str(root), ".", "smart", ""))
    assert len(res_empty) == 0

def test_cr06_relative_to_root():
    """CR-06/07: Ensure relative_to handles files in the root directory correctly."""
    root = AUDIT_TEMP / "root_test"
    root.mkdir()
    f1 = root / "in_root.txt"
    f1.write_text("data")
    
    flattened = FileUtils.flatten_paths([str(f1)], root_dir=str(root))
    assert len(flattened) == 1
    assert "in_root.txt" in flattened[0]

def test_cr04_action_bridge_refactor():
    """CR-04: Verify ActionBridge refactoring results in correct command preparation."""
    template = "echo {name} in {parent_name}"
    path = "C:/Test/file.txt" if os.name == 'nt' else "/tmp/test/file.txt"
    root = "C:/Test" if os.name == 'nt' else "/tmp/test"
    
    import pathlib
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr(pathlib.Path, "exists", lambda x: True)
        cmd, is_shell, ctx = ActionBridge._prepare_execution(template, path, root)
        
        if os.name == 'nt':
            # On Windows, shlex.split with posix=False used in _prepare_execution should preserve casing 
            # unless PathValidator.norm_path was called.
            # Here we check the resulting list.
            assert [c.lower() for c in cmd] == ["echo", "file.txt", "in", "test"]
            assert is_shell is False
        else:
            assert cmd == ["echo", "file.txt", "in", "test"]
            assert is_shell is False

def test_cr24_delete_readonly_file():
    """CR-24: Ensure delete_file can handle read-only files on Windows."""
    f = AUDIT_TEMP / "readonly.txt"
    f.write_text("can't touch this")
    
    # Make it read-only
    mode = os.stat(f).st_mode
    os.chmod(f, mode & ~stat.S_IWRITE)
    
    # Verify it's read-only
    with pytest.raises(IOError):
        with open(f, 'w') as fh:
            fh.write("fail")
            
    assert FileOps.delete_file(str(f)) is True
    assert not f.exists()

def test_cr09_desktop_security_logic():
    """CR-09: Verify desktop-level security validation prevents out-of-root access."""
    root = AUDIT_TEMP / "safe_root"
    root.mkdir()
    unsafe = AUDIT_TEMP / "unsafe.txt"
    unsafe.write_text("evil")
    
    assert PathValidator.is_safe(str(unsafe), str(root)) is False
    
    safe = root / "inner.txt"
    safe.write_text("good")
    assert PathValidator.is_safe(str(safe), str(root)) is True
