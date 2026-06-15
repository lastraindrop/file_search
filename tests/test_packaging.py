"""Packaging integrity smoke tests (BUG-D1/D2/Doc5 regression)."""

import pathlib

import tomllib


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
