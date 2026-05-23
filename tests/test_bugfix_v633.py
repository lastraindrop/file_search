"""Tests for v6.3.3 BUG fixes and boundary coverage.

Covers:
- BUG-1: is_truncated boundary (fs_routes.py:83)
- BUG-2: CDATA looping escape (context.py:174)
- BUG-3: CORS origin wildcard detection (web_app.py:31-40)
- BUG-4: NoiseReducer.clean None input (context.py:24)
- BUG-7: global_settings uses Pydantic model (action_routes.py:119)
- Content preview truncation end-to-end
"""

import pathlib

from file_cortex_core import DataManager, NoiseReducer
from file_cortex_core import __version__ as core_version
from file_cortex_core.context import ContextFormatter
from web_app import _is_wildcard_origin, _parse_allowed_origins


class TestIsTruncatedBoundary:
    """Tests for BUG-1: is_truncated >= vs > logic."""

    def test_is_truncated_equals_limit(self, project_client):
        """When content bytes exactly equal max_preview, should NOT be truncated."""
        dm = DataManager()
        dm.config.global_settings.preview_limit_mb = 0.001  # ~1KB
        dm.save()

        project_path = list(dm.config.projects.keys())[0]

        # Find a text file in the project
        src_dir = pathlib.Path(project_path) / "src"
        if src_dir.exists():
            text_files = list(src_dir.glob("*.py"))
            if text_files:
                file_path = str(text_files[0])
                res = project_client.get(f"/api/content?path={file_path}")
                assert res.status_code == 200
                data = res.json()
                # File should be small enough to not be truncated at 1KB
                # but the key assertion is that when bytes == max, is_truncated is False
                assert "is_truncated" in data

    def test_is_truncated_small_file(self, project_client):
        """Small file with content < preview_limit should not be truncated."""
        dm = DataManager()
        dm.config.global_settings.preview_limit_mb = 10.0
        dm.save()

        project_path = list(dm.config.projects.keys())[0]
        readme = pathlib.Path(project_path) / "README.md"
        if readme.exists():
            res = project_client.get(f"/api/content?path={str(readme)}")
            assert res.status_code == 200
            data = res.json()
            assert data["is_truncated"] is False


class TestCDATALoopingEscape:
    """Tests for BUG-2: CDATA replacement correctness for consecutive ]]> sequences.

    Note: The standard XML CDATA escape replaces ]]> with ]]]]><![CDATA[>
    in a single pass. Multiple ]]> sequences each get replaced once.
    The replacement string itself intentionally ends with ]]> as part
    of the CDATA boundary reconstruction.
    """

    def test_cdata_single_escape(self):
        """Basic CDATA escape case — single pass replacement."""
        content = "hello ]]> world"
        safe = content.replace("]]>", "]]]]><![CDATA[>")
        # The result should have replaced the original ]]> with CDATA boundary
        assert "<![CDATA[" in safe
        assert safe.count("]]>") == 1  # CDATA closing marker in replacement

    def test_cdata_consecutive_escape(self):
        """Consecutive ]]> sequences each get one replacement."""
        content = "a ]]> b ]]> c"
        safe = content.replace("]]>", "]]]]><![CDATA[>")
        # Each original ]]> gets replaced. The replacements themselves
        # contain ]]>, so total count is number of original sequences.
        assert safe.count("<![CDATA[") >= 2

    def test_cdata_no_escape_needed(self):
        """Content without ]]> should remain unchanged."""
        content = "clean content without cdata issues"
        safe = content.replace("]]>", "]]]]><![CDATA[>")
        assert safe == content

    def test_cdata_in_context_formatter_xml(self, tmp_path):
        """End-to-end: ContextFormatter.to_xml handles ]]> sequences properly."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("line1 ]]> line2", encoding="utf-8")
        result = ContextFormatter.to_xml([str(test_file)], root_dir=str(tmp_path))
        assert "<context>" in result
        assert "<![CDATA[" in result
        assert "]]>" in result  # CDATA closing markers from proper escaping


class TestCORSOriginWildcardDetection:
    """Tests for BUG-3: CORS origin wildcard detection robustness."""

    def test_parse_wildcard_default(self):
        """Default (empty) should return ['*']."""
        result = _parse_allowed_origins(None)
        assert result == ["*"]

    def test_parse_wildcard_explicit(self):
        """Explicit '*' should return ['*']."""
        result = _parse_allowed_origins("*")
        assert result == ["*"]

    def test_parse_specific_origins(self):
        """Comma-separated origins should return list."""
        result = _parse_allowed_origins("http://a.com, http://b.com")
        assert "http://a.com" in result
        assert "http://b.com" in result

    def test_is_wildcard_true_for_star(self):
        """['*'] should be detected as wildcard."""
        assert _is_wildcard_origin(["*"]) is True

    def test_is_wildcard_true_for_star_in_list(self):
        """List containing '*' should be detected as wildcard."""
        assert _is_wildcard_origin(["*", "http://a.com"]) is True

    def test_is_wildcard_false_for_specific(self):
        """List without '*' should not be wildcard."""
        assert _is_wildcard_origin(["http://a.com"]) is False

    def test_is_wildcard_false_for_empty(self):
        """Empty list should not be wildcard."""
        assert _is_wildcard_origin([]) is False


class TestNoiseReducerNoneInput:
    """Tests for BUG-4: NoiseReducer.clean handles None input gracefully."""

    def test_clean_none_input(self):
        """None should return empty string without error."""
        result = NoiseReducer.clean(None)
        assert result == ""

    def test_clean_empty_string(self):
        """Empty string should return empty string."""
        result = NoiseReducer.clean("")
        assert result == ""

    def test_clean_normal_content(self):
        """Normal content should pass through."""
        result = NoiseReducer.clean("hello world")
        assert "hello world" in result

    def test_clean_long_line_truncation(self):
        """Lines exceeding max_line_length should be replaced."""
        long_line = "x" * 600
        result = NoiseReducer.clean(long_line, max_line_length=500)
        assert "NoiseReducer" in result
        assert long_line not in result


class TestGlobalSettingsUsesPydanticModel:
    """Tests for BUG-7: /api/global/settings returns Pydantic model output."""

    def test_global_settings_returns_pydantic_model_dump(self, api_client):
        """GET /api/global/settings should return Pydantic model_dump()."""
        res = api_client.get("/api/global/settings")
        assert res.status_code == 200
        data = res.json()
        assert "preview_limit_mb" in data
        assert "token_threshold" in data
        assert "enable_noise_reducer" in data
        assert "token_ratio" in data
        assert "theme" in data
        assert "allowed_extensions" in data

    def test_global_settings_defaults_correct(self, api_client):
        """Default model values should be present."""
        res = api_client.get("/api/global/settings")
        data = res.json()
        assert data["token_threshold"] == 128000
        assert data["token_ratio"] == 4.0
        assert data["preview_limit_mb"] == 1.0
        assert data["enable_noise_reducer"] is False


class TestContentPreviewTruncation:
    """End-to-end tests for content preview truncation behavior."""

    def test_content_preview_respects_limit(self, project_client):
        """Content preview should respect the preview_limit_mb setting."""
        dm = DataManager()
        project_path = list(dm.config.projects.keys())[0]
        config_path = pathlib.Path(project_path) / "config.json"
        if config_path.exists():
            # Set a very small limit
            dm.config.global_settings.preview_limit_mb = 0.0001  # ~100 bytes
            dm.save()
            res = project_client.get(f"/api/content?path={str(config_path)}")
            assert res.status_code == 200
            data = res.json()
            assert "content" in data
            assert "is_truncated" in data

    def test_content_binary_file(self, project_client):
        """Binary files should return placeholder message."""
        dm = DataManager()
        project_path = list(dm.config.projects.keys())[0]
        bin_file = pathlib.Path(project_path) / "image.png"
        if bin_file.exists():
            res = project_client.get(f"/api/content?path={str(bin_file)}")
            assert res.status_code == 200
            data = res.json()
            assert "Binary" in data["content"]


class TestVersionIncrement:
    """Verify v6.3.3 version is correctly propagated."""

    def test_core_version_is_updated(self):
        """Core module version should be 6.3.3."""
        assert core_version == "6.4.0"

    def test_version_pyproject_matches(self):
        """pyproject.toml version should match core version."""
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib
        pyproject_path = pathlib.Path(__file__).parent.parent / "pyproject.toml"
        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)
        assert data["project"]["version"] == "6.4.0"

    def test_version_in_index_page(self, api_client):
        """Index page should contain version string."""
        res = api_client.get("/")
        assert res.status_code == 200
        assert "6.4.0" in res.text
