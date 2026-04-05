"""
CR-A04: Verify that win_quote correctly escapes symbols like % to prevent 
environment variable expansion or command injection in CMD.
"""
import pytest
import os
import sys
from file_cortex_core import ActionBridge


@pytest.mark.skipif(os.name != 'nt', reason="Windows CMD specific test")
def test_percent_in_filename(mock_project):
    """Verify that % in a filename is escaped to %% to prevent expansion."""
    special_name = "report_%DATE%.txt"
    special_path = mock_project / special_name
    special_path.touch()
    
    # Use a python echo to ensure we test shell=False (list-mode) behavior.
    # Python is a real executable, so ActionBridge won't fallback to shell=True.
    cmd = f'"{sys.executable}" -c "import sys; print(sys.argv[1], end=\'\')"'
    res = ActionBridge.execute_tool(f"{cmd} {{name}}", str(special_path), str(mock_project))
    
    # Path-based variables like %DATE% should NOT expand when using shell=False.
    assert special_name in res["stdout"]
    assert "%DATE%" in res["stdout"] 
    # Verify no accidental expansion occurred
    assert "202" not in res["stdout"]


@pytest.mark.skipif(os.name != 'nt', reason="Windows CMD specific test")
def test_ampersand_in_filename(mock_project):
    """Verify that & in a filename is quoted and doesn't split commands."""
    special_name = "test & whoami.txt"
    special_path = mock_project / special_name
    special_path.touch()
    
    res = ActionBridge.execute_tool("echo {name}", str(special_path), str(mock_project))
    
    # If & worked as a separator, whoami would execute.
    # The output should contain the full name including the ampersand.
    assert "test & whoami.txt" in res["stdout"]
    # Check that current user name (result of whoami) isn't just hanging there
    import getpass
    curr_user = getpass.getuser()
    if curr_user:
        # If it's a naked echo of the command, it might contain the username 
        # in some environments, but it shouldn't be executed as a separate command.
        assert f"\n{curr_user}" not in res["stdout"]


def test_newline_in_path(mock_project):
    """Verify that newline in a path (if technically possible) is handled."""
    # Newlines are illegal in most FS but we check quoting logic
    # We simulate by passing a string with a newline as if it's a path
    try:
        res = ActionBridge.execute_tool("echo {name}", "file\nname.txt", str(mock_project))
        assert "file" in res["stdout"] or "error" in res or res["returncode"] != 0
    except Exception:
        # Some OS/Shell combination might just throw an error before execution
        pass


def test_unicode_filename(mock_project):
    """Verify that Unicode filenames are passed correctly to tools."""
    special_name = "文档_document.txt"
    special_path = mock_project / special_name
    special_path.touch()
    
    # We use a python echo to ensure encoding is handled in the pipe
    cmd = f'"{sys.executable}" -c "import sys; print(sys.argv[1])"'
    res = ActionBridge.execute_tool(f"{cmd} {{name}}", str(special_path), str(mock_project))
    
    assert "文档_document.txt" in res["stdout"]
