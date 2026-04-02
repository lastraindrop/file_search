import pytest
import pathlib
import os
from file_cortex_core import PathValidator

@pytest.mark.parametrize("path_str, expected_contains", [
    ("C:/Users/Test", "c:/users/test" if os.name == 'nt' else "C:/Users/Test"),
    ("E:/Work/Proj", "e:/work/proj" if os.name == 'nt' else "E:/Work/Proj"),
    ("/home/user/data", f"{pathlib.Path(os.getcwd()).anchor.lower().replace(os.sep, '/')}home/user/data" if os.name == 'nt' else "/home/user/data"),
])
def test_norm_path_platform_behavior(path_str, expected_contains):
    norm = PathValidator.norm_path(path_str)
    if os.name == 'nt':
        # On Windows, abspath often prefixes with current drive's anchor
        assert norm.lower() == expected_contains.lower()
    else:
        assert norm == expected_contains

def test_norm_path_consistency():
    p1 = "C:\\TEMP\\FILE.txt" if os.name == 'nt' else "/TMP/FILE.txt"
    p2 = "c:/temp/file.txt" if os.name == 'nt' else "/TMP/FILE.txt"
    
    assert PathValidator.norm_path(p1) == PathValidator.norm_path(p2)

def test_norm_path_trailing_slash():
    p = "C:/Data/" if os.name == 'nt' else "/data/"
    norm = PathValidator.norm_path(p)
    assert not norm.endswith("/")
