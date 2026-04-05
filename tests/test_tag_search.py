import pytest
import pathlib
from file_cortex_core.search import search_generator

def test_search_with_tags(tmp_path):
    # Setup dummy project
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('hello')")
    (tmp_path / "src" / "utils.py").write_text("def util(): pass")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_main.py").write_text("import main")
    (tmp_path / "README.md").write_text("Docs")

    # 1. Positive tags: 'src' and 'main'
    results = list(search_generator(tmp_path, "", "smart", "", positive_tags=["src", "main"]))
    names = [pathlib.Path(r['path']).name for r in results]
    assert "main.py" in names
    assert "test_main.py" not in names # test_main.py is in 'tests', not 'src'
    
    # 2. Negative tags: '-test'
    results = list(search_generator(tmp_path, "py", "smart", "", negative_tags=["test"]))
    names = [pathlib.Path(r['path']).name for r in results]
    assert "main.py" in names
    assert "utils.py" in names
    assert "test_main.py" not in names

    # 3. Regex tags: /u[t|l]/
    results = list(search_generator(tmp_path, "", "smart", "", positive_tags=["/u[t|l]/"]))
    names = [pathlib.Path(r['path']).name for r in results]
    assert "utils.py" in names
    assert "main.py" not in names
