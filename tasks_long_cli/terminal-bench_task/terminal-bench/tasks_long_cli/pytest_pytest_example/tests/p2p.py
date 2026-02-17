from pathlib import Path

# Does the source file exist
def test_source_file_exists_example():
    source_path = Path("/app/task_dir/source.py")
    assert source_path.exists(), f"File {source_path} does not exist"

# Is the source file been modified
def test_source_file_content():
    target_path = Path("/app/task_dir/source.py")
    
    actual_content = target_path.read_text().strip()
    expected_content = """def test(a):
    return a"""
    
    assert actual_content == expected_content, (
        f"Expected content:\n{expected_content}\n\nBut got:\n{actual_content}"
    )