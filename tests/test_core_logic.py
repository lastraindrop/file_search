import pytest
import pathlib
from core_logic import FileUtils, DataManager, search_generator

def test_data_manager(clean_config):
    dm = DataManager()
    dm.data["last_directory"] = "/test/path"
    dm.save()
    
    # Reload and verify
    dm2 = DataManager()
    assert dm2.data["last_directory"] == "/test/path"

def test_file_utils_binary(mock_project):
    assert FileUtils.is_binary(mock_project / "image.png") == True
    assert FileUtils.is_binary(mock_project / "src" / "main.py") == False

def test_file_utils_lang_tags():
    assert FileUtils.get_language_tag(".py") == "python"
    assert FileUtils.get_language_tag(".js") == "javascript"
    assert FileUtils.get_language_tag(".mdfk") == ""

@pytest.mark.parametrize("query, mode, expected_count", [
    ("main", "smart", 1),
    ("utils", "smart", 1),
    ("print", "content", 1),
    ("console", "content", 1),
    ("zxy", "smart", 0),
])
def test_search_basic(mock_project, query, mode, expected_count):
    results = list(search_generator(mock_project, query, mode, ""))
    assert len(results) == expected_count

def test_search_inverse(mock_project):
    # Name Inverse: match files NOT containing 'main'
    # src/main.py (matches 'main'), src/utils.js, image.png, .gitignore. 
    # Total files in current mock: src/main.py, src/utils.js, image.png, .gitignore, error.log, node_modules (excluded)
    # Actually wait: search_generator excludes log/node_modules if told to. 
    # If excludes="", it should match everything.
    
    # Standard: 'main' -> [src/main.py]
    # Inverse: NOT 'main' -> [src/utils.js, image.png, .gitignore] (excluding others if they exist)
    results = list(search_generator(mock_project, "main", "smart", "", is_inverse=True))
    # We expect 3 matches based on the mock_project structure
    assert len(results) == 3

def test_search_content_inverse(mock_project):
    # Content Inverse: files NOT containing 'print'
    # src/main.py (contains 'print'), src/utils.js (contains 'console'), image.png (binary), .gitignore (contains '*.log')
    # If mode='content', it skips binary.
    # Standard: 'print' -> [src/main.py]
    # Inverse: 'print' -> [src/utils.js, .gitignore] (skips binary naturally)
    results = list(search_generator(mock_project, "print", "content", "", is_inverse=True))
    assert len(results) == 2

def test_gitignore_logic(mock_project):
    # node_modules and error.log should be ignored
    results = list(search_generator(mock_project, "", "smart", ""))
    paths = [p for p, t in results]
    assert any("main.py" in p for p in paths)
    assert not any("error.log" in p for p in paths)
    assert not any("node_modules" in p for p in paths)
