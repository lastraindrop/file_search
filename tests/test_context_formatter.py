from file_cortex_core import ContextFormatter, NoiseReducer


def test_to_markdown_with_prompt(mock_project):
    """Verify Markdown export with prompt prefix injection."""
    files = [str(mock_project / "src" / "main.py")]
    prompt = "SYSTEM_INSTRUCTION: Analyze this code."
    res = ContextFormatter.to_markdown(files, root_dir=str(mock_project), prompt_prefix=prompt)
    assert prompt in res
    assert "File: src/main.py" in res or "File: src\\main.py" in res
    assert "```python" in res

def test_to_xml_cdata_escaping(mock_project):
    """Verify XML export handle CDATA nesting correctly."""
    # Create file with ]]> which is a CDATA end marker
    malicious_f = mock_project / "evil.txt"
    malicious_f.write_text("Look at this: ]]> oh no", encoding="utf-8")

    files = [str(malicious_f)]
    res = ContextFormatter.to_xml(files, root_dir=str(mock_project))
    assert "<context>" in res
    # The ]]> should be handled by replacing with ]]] ]><![CDATA[>
    assert "]]]]><![CDATA[>" in res

def test_to_xml_empty_files(tmp_path):
    """Empty file list should produce valid empty XML."""
    res = ContextFormatter.to_xml([], root_dir=str(tmp_path))
    assert "<context>" in res
    assert "</context>" in res
    assert "<file " not in res

def test_blueprint_depth_limit(stress_project):
    from file_cortex_core import FileUtils
    # max_depth=0 allows showing the root's direct children but not their contents
    tree = FileUtils.generate_ascii_tree(str(stress_project), excludes_str="", max_depth=0)
    assert "stress_project" in tree
    assert "dir_0" in tree
    assert "file_0.txt" not in tree

def test_noise_reducer_base64():
    """Verify base64/minified detection."""
    b64_str = "SGVsbG8gd29ybGQ=" * 100 # Large repetitive block
    res = NoiseReducer.clean(b64_str)
    assert "chars skipped by NoiseReducer" in res

def test_noise_reducer_none_input():
    """None or empty input to noise reducer."""
    assert NoiseReducer.clean("") == ""
    assert NoiseReducer.clean(None) == ""
