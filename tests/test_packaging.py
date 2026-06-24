"""Packaging integrity smoke tests (BUG-D1/D2/Doc5 regression)."""

import pathlib
import re

import tomllib

EXPECTED_TEST_COUNT = 661


def test_pyproject_declares_routers() -> None:
    """BUG-D1: pyproject.toml must list routers in packages."""
    pyproject = pathlib.Path(__file__).resolve().parent.parent / "pyproject.toml"
    with open(pyproject, "rb") as f:
        data = tomllib.load(f)
    packages = data["tool"]["setuptools"].get("packages", [])
    assert "routers" in packages, f"routers missing from packages: {packages}"


def test_pyproject_declares_entry_modules() -> None:
    """BUG-D1: mcp_server and build_exe must be declared as py-modules."""
    pyproject = pathlib.Path(__file__).resolve().parent.parent / "pyproject.toml"
    with open(pyproject, "rb") as f:
        data = tomllib.load(f)
    py_modules = data["tool"]["setuptools"].get("py-modules", [])
    assert "mcp_server" in py_modules, f"mcp_server missing: {py_modules}"
    assert "build_exe" in py_modules, f"build_exe missing: {py_modules}"


def test_pyproject_declares_mcp_optional_dep() -> None:
    """BUG-D2: mcp must be declared as an optional dependency."""
    pyproject = pathlib.Path(__file__).resolve().parent.parent / "pyproject.toml"
    with open(pyproject, "rb") as f:
        data = tomllib.load(f)
    optional = data["project"].get("optional-dependencies", {})
    assert "mcp" in optional, (
        f"Missing [project.optional-dependencies].mcp in: {list(optional.keys())}"
    )
    assert any("mcp" in dep for dep in optional["mcp"]), (
        f"mcp dep not found in: {optional['mcp']}"
    )


def test_pyproject_declares_mcp_console_script() -> None:
    """BUG-Doc5: fctx-mcp console script must be declared."""
    pyproject = pathlib.Path(__file__).resolve().parent.parent / "pyproject.toml"
    with open(pyproject, "rb") as f:
        data = tomllib.load(f)
    scripts = data["project"].get("scripts", {})
    assert scripts.get("fctx-mcp") == "mcp_server:main", (
        f"fctx-mcp not found or wrong target: {scripts}"
    )


def test_routers_importable() -> None:
    """BUG-D1: Routers package must be importable after changes."""
    import routers  # noqa: F401
    from routers.http_routes import router  # noqa: F401
    from routers.ws_routes import router as ws_router  # noqa: F401


def test_entry_modules_importable() -> None:
    """BUG-D1: Entry-point modules must be importable."""
    import fctx  # noqa: F401
    import mcp_server  # noqa: F401
    import web_app  # noqa: F401


# ---------------------------------------------------------------------------
# Version & docs consistency regression guards
# ---------------------------------------------------------------------------


def test_pyproject_version_matches_core_version() -> None:
    """pyproject.toml version must agree with file_cortex_core.__version__."""
    from file_cortex_core import __version__

    root = pathlib.Path(__file__).resolve().parent.parent
    with open(root / "pyproject.toml", "rb") as f:
        data = tomllib.load(f)
    declared = data["project"]["version"]
    assert declared == __version__, (
        f"pyproject.toml version '{declared}' != core __version__ '{__version__}'"
    )


def test_readme_version_claims_match_core_version() -> None:
    """Both README files must reference the current core version string."""
    from file_cortex_core import __version__

    root = pathlib.Path(__file__).resolve().parent.parent
    for readme_file in ("README.md", "tests/README.md"):
        content = (root / readme_file).read_text(encoding="utf-8")
        assert __version__ in content, (
            f"{readme_file} does not reference version {__version__}"
        )


def test_readme_test_count_claims_are_consistent() -> None:
    """README.md and tests/README.md must agree with the current test count."""
    root = pathlib.Path(__file__).resolve().parent.parent
    main_readme = (root / "README.md").read_text(encoding="utf-8")
    tests_readme = (root / "tests/README.md").read_text(encoding="utf-8")

    # Matches "测试: 652" / "**测试数**: 652" style headlines (CJK-aware).
    pattern = re.compile(r"测试数?\D{0,10}(\d+)")

    main_match = pattern.search(main_readme)
    tests_match = pattern.search(tests_readme)
    assert main_match, "README.md has no '测试: <N>' headline claim"
    assert tests_match, "tests/README.md has no '测试数: <N>' headline claim"
    assert main_match.group(1) == tests_match.group(1), (
        f"Test-count claims diverge: README.md={main_match.group(1)}, "
        f"tests/README.md={tests_match.group(1)}"
    )
    assert int(main_match.group(1)) == EXPECTED_TEST_COUNT


def test_tests_readme_table_sums_to_headline() -> None:
    """tests/README.md per-layer counts must sum to the documented total."""
    root = pathlib.Path(__file__).resolve().parent.parent
    tests_readme = (root / "tests" / "README.md").read_text(encoding="utf-8")

    row_pattern = re.compile(r"^\| \*\*(?!总计).+?\*\* \| .+? \| (\d+) \|", re.MULTILINE)
    row_counts = [int(match.group(1)) for match in row_pattern.finditer(tests_readme)]

    assert row_counts, "No test-count rows found in tests/README.md"
    assert sum(row_counts) == EXPECTED_TEST_COUNT, (
        f"tests/README.md table sums to {sum(row_counts)}, "
        f"expected {EXPECTED_TEST_COUNT}"
    )


# ---------------------------------------------------------------------------
# Dependency declaration consistency
# ---------------------------------------------------------------------------


def _normalize_dep_names(deps: list[str]) -> set[str]:
    """Extracts lowercased PEP 508 package names from requirement strings.

    Strips comments, environment markers, extras and version specifiers so that
    only the canonical package name remains (e.g. ``python-multipart``).
    """
    names: set[str] = set()
    for dep in deps:
        dep = dep.split("#")[0].split(";")[0].strip()
        if not dep:
            continue
        match = re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*)", dep)
        if match:
            names.add(match.group(1).lower().replace("_", "-"))
    return names


def test_requirements_txt_matches_pyproject_dependencies() -> None:
    """requirements.txt and pyproject.toml must declare the same package set."""
    root = pathlib.Path(__file__).resolve().parent.parent

    with open(root / "pyproject.toml", "rb") as f:
        data = tomllib.load(f)
    pyproject_names = _normalize_dep_names(data["project"].get("dependencies", []))

    req_lines = (root / "requirements.txt").read_text(encoding="utf-8").splitlines()
    req_names = _normalize_dep_names(
        [line for line in req_lines if line.strip() and not line.strip().startswith("#")]
    )

    # Guard against vacuous pass when both sides parse to empty.
    assert pyproject_names, "pyproject.toml declared no dependencies (parse failure?)"
    assert pyproject_names == req_names, (
        f"Dependency declarations diverge:\n"
        f"  pyproject.toml only: {sorted(pyproject_names - req_names)}\n"
        f"  requirements.txt only: {sorted(req_names - pyproject_names)}"
    )


# ---------------------------------------------------------------------------
# Schema dict-size validator direct regression (BUG-W9)
# ---------------------------------------------------------------------------


def test_validate_dict_size_accepts_small_dict() -> None:
    """_validate_dict_size must pass-through dicts under MAX_DICT_JSON_BYTES."""
    from routers.schemas import _validate_dict_size

    small = {"key": "value", "nested": {"a": 1, "b": [1, 2, 3]}}
    assert _validate_dict_size(small) == small


def test_validate_dict_size_rejects_oversized_dict() -> None:
    """_validate_dict_size must reject dicts exceeding MAX_DICT_JSON_BYTES."""
    import pytest

    from routers.schemas import MAX_DICT_JSON_BYTES, _validate_dict_size

    oversized = {"data": "x" * (MAX_DICT_JSON_BYTES + 100)}
    with pytest.raises(ValueError, match="too large"):
        _validate_dict_size(oversized)


def test_validate_dict_size_rejects_non_serializable() -> None:
    """_validate_dict_size must reject non-JSON-serializable values."""
    import pytest

    from routers.schemas import _validate_dict_size

    with pytest.raises(ValueError, match="not JSON-serializable"):
        _validate_dict_size({"bad": object()})


# ---------------------------------------------------------------------------
# Web app version endpoint regression
# ---------------------------------------------------------------------------


def test_web_app_whoami_returns_core_version() -> None:
    """The /api/whoami endpoint must report the current core version.

    Uses TestClient (already imported by conftest) so the routing, middleware
    pass-through (no API token set) and response body are all exercised.
    """
    from fastapi.testclient import TestClient

    from file_cortex_core import __version__
    from web_app import app

    response = TestClient(app).get("/api/whoami")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"] == __version__
