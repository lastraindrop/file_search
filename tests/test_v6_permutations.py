import pytest
import pathlib
from file_cortex_core import search_generator, FileUtils

@pytest.mark.parametrize("search_mode", ["smart", "exact", "regex", "content"])
@pytest.mark.parametrize("case_sensitive", [True, False])
@pytest.mark.parametrize("is_inverse", [True, False])
def test_search_parameter_permutations(mock_project, search_mode, case_sensitive, is_inverse):
    """Exhaustive test of search parameter combinations."""
    query = "main"
    if search_mode == 'regex':
        query = "m.*\\.py"
    
    results = list(search_generator(
        root_dir=str(mock_project),
        search_text=query,
        search_mode=search_mode,
        manual_excludes="",
        case_sensitive=case_sensitive,
        is_inverse=is_inverse
    ))
    
    # Generic assertions: result structure
    for r in results:
        assert "path" in r
        assert "match_type" in r
        assert "mtime" in r
        
    # Logic check for a known file: src/main.py
    target = "main.py" if case_sensitive else "MAIN.PY"
    # Note: search_generator processes query based on case_sensitive
    
    has_main = any("main.py" in r["path"] for r in results)
    
    # In normal mode, should find main.py (unless it's content mode and query is 'main' but file content doesn't have it)
    # mock_project/src/main.py content is "print('hello')" -> has 'hello', not 'main'
    
    if search_mode == 'content':
        # Should find 'print' in main.py
        res_print = list(search_generator(str(mock_project), "print", "content", ""))
        assert any("main.py" in r["path"] for r in res_print)
    elif not is_inverse:
        assert has_main or search_mode == 'content'
    else:
        # Inverse mode: main.py should NOT be in results if it matches query normally
        assert not has_main

@pytest.mark.parametrize("prefix,suffix,sep", [
    ("@", "/", "\\n"),
    ("file:", "[dir]", " "),
    ("", "", ",")
])
def test_path_formatting_permutations(mock_project, prefix, suffix, sep):
    """Verify that FormatUtils handles formatting parameters, including dir_suffix."""
    from file_cortex_core import FormatUtils
    # Include a directory (src) to test dir_suffix
    files = [str(mock_project / "src"), str(mock_project / "README.md")]
    
    output = FormatUtils.collect_paths(files, mode='absolute', separator=sep, file_prefix=prefix, dir_suffix=suffix)
    
    assert f"{prefix}" in output
    if suffix:
        assert suffix in output
    assert (sep.replace('\\n', '\n') if '\\n' in sep else sep) in output

def test_search_with_tags_combinations(mock_project):
    """Verify searching with both text and recursive tag-like syntax."""
    # Tag-like syntax: /pattern/
    results = list(search_generator(
        root_dir=str(mock_project),
        search_text="",
        search_mode="smart",
        manual_excludes="",
        positive_tags=["/.*\\.py$/"] # Find all .py files
    ))
    
    names = [pathlib.Path(r["path"]).name for r in results]
    assert "main.py" in names
    assert all(n.endswith(".py") for n in names)

def test_search_negative_tags_exclusion(mock_project):
    """Verify that negative tags correctly exclude files even if they match positive query."""
    results = list(search_generator(
        root_dir=str(mock_project),
        search_text="py",
        search_mode="smart",
        manual_excludes="",
        negative_tags=["main"] # Match everything with 'py' but NOT 'main'
    ))
    
    names = [pathlib.Path(r["path"]).name for r in results]
    assert "main.py" not in names
    # Should still have other things matching 'py' if any (legacy_zh.py in noisy_project, but here we use mock_project)
    # mock_project has main.py. If we have others, they'd stay.
