"""
CR-C12: Verify that NoiseReducer correctly replaces long lines with digest markers.
"""
import pytest
from file_cortex_core import NoiseReducer


def test_empty_content():
    """Verify that empty content returns empty string."""
    assert NoiseReducer.clean("") == ""
    assert NoiseReducer.clean(None) == ""


def test_long_line_replacement():
    """Verify that a line longer than max_line_length is replaced."""
    long_line = "A" * 2000
    short_line = "Hello World"
    content = f"{short_line}\n{long_line}\n{short_line}"
    
    # Process with default limit (1000)
    result = NoiseReducer.clean(content)
    
    lines = result.splitlines()
    assert len(lines) == 3
    assert lines[0] == short_line
    assert "skipped by NoiseReducer" in lines[1]
    assert lines[2] == short_line


def test_custom_max_length():
    """Verify that a custom limit works."""
    line = "A" * 50
    content = f"{line}\n{line}"
    
    # Process with limit 40
    result = NoiseReducer.clean(content, max_line_length=40)
    
    assert "skipped by NoiseReducer" in result


def test_normal_content_preserved():
    """Verify that short lines are not touched."""
    content = "Line 1\nLine 2\nLine 3"
    assert NoiseReducer.clean(content) == content
