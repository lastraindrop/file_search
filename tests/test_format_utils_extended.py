"""
CR-C11 / D-05: Extended tests for FormatUtils covering GB formatting 
and edge cases in format_size, format_number, estimate_tokens.
"""
import pytest
from file_cortex_core import FormatUtils


def test_format_size_gb():
    """Verify GB formatting for large file sizes."""
    # 1 GB exactly
    assert FormatUtils.format_size(1024 * 1024 * 1024) == "1.0 GB"
    # 2.5 GB
    assert "2.5 GB" == FormatUtils.format_size(int(2.5 * 1024 * 1024 * 1024))


def test_format_size_boundary():
    """Verify correct boundary between MB and GB."""
    # Just under 1 GB (1023 MB)
    just_under_gb = 1023 * 1024 * 1024
    result = FormatUtils.format_size(just_under_gb)
    assert "MB" in result
    # Exactly 1 GB
    exactly_gb = 1024 * 1024 * 1024
    result = FormatUtils.format_size(exactly_gb)
    assert "GB" in result


def test_format_size_zero():
    """Verify 0 bytes formatting."""
    assert FormatUtils.format_size(0) == "0 B"


def test_format_size_one_byte():
    """Verify 1 byte formatting."""
    assert FormatUtils.format_size(1) == "1 B"


def test_estimate_tokens_unicode():
    """Verify token estimation with CJK characters."""
    text = "你好世界" * 100
    tokens = FormatUtils.estimate_tokens(text)
    assert tokens > 0


def test_estimate_tokens_mixed():
    """Verify token estimation with mixed content (weighted for CJK)."""
    text = "Hello 你好 World 世界"
    tokens = FormatUtils.estimate_tokens(text)
    assert tokens > 0
    # New weighted formula gives 5 for this string: int((13/4) + (4/1.5)) = 5
    assert tokens > len(text) // 4 
    assert tokens == 5
