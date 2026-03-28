import pytest
import pathlib
import os
from file_cortex_core import FileUtils, FormatUtils, ContextFormatter

def test_format_utils_size():
    """Verify various size formatting outputs."""
    assert FormatUtils.format_size(500) == "500 B"
    assert FormatUtils.format_size(1024) == "1.0 KB"
    assert "MB" in FormatUtils.format_size(2048 * 1024)

def test_token_estimation_logic():
    """Verify refined token estimation (approx 4 chars/token)."""
    text = "const a = 10; // This is a test string"
    # Basic check: should be non-zero and roughly 1/4 the length
    tokens = FormatUtils.estimate_tokens(text)
    assert tokens > 0
    assert tokens == len(text) // 4
    
    # Null cases
    assert FormatUtils.estimate_tokens("") == 0
    assert FormatUtils.estimate_tokens(None) == 0

def test_binary_detection(mock_project):
    """Verify that binary vs text detection is accurate."""
    # Text
    main_py = mock_project / "src" / "main.py"
    assert FileUtils.is_binary(main_py) is False
    
    # Binary
    data_bin = mock_project / "data.bin"
    assert FileUtils.is_binary(data_bin) is True
    
    # Image (Binary)
    img_png = mock_project / "image.png"
    assert FileUtils.is_binary(img_png) is True

def test_language_tag_mapping():
    """Verify file extension to language tag mapping for markdown."""
    assert FileUtils.get_language_tag(".py") == "python"
    assert FileUtils.get_language_tag(".JS") == "javascript"
    assert FileUtils.get_language_tag(".unknown_xyz") == ""

def test_context_formatter_with_template(mock_project):
    """Verify markdown output with prompt prefix/templates."""
    files = [str(mock_project / "src" / "main.py")]
    prefix = "Please review this code:"
    
    output = ContextFormatter.to_markdown(files, root_dir=mock_project, prompt_prefix=prefix)
    
    assert prefix in output
    # Path-agnostic check
    assert "File: src" in output and "main.py" in output
    assert "```python" in output
    assert "print('hello')" in output

def test_gitignore_ignore_logic(mock_project):
    """Verify respects gitignore and manual excludes."""
    git_spec = FileUtils.get_gitignore_spec(mock_project)
    
    # Ignored by gitignore (error.log)
    rel_path_log = pathlib.Path("error.log")
    assert FileUtils.should_ignore("error.log", rel_path_log, [], git_spec) is True
    
    # Ignored by manual excludes
    rel_path_js = pathlib.Path("src/utils.js")
    assert FileUtils.should_ignore("utils.js", rel_path_js, ["*.js"], git_spec) is True
    
    # Safe
    rel_path_py = pathlib.Path("src/main.py")
    assert FileUtils.should_ignore("main.py", rel_path_py, ["*.txt"], git_spec) is False
