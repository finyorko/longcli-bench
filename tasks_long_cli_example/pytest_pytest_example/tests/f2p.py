from pathlib import Path

# If the target file exist
def test_target_file_exists_example():
    target_path = Path("/app/task_dir/target.py")
    assert target_path.exists(), f"File {target_path} does not exist"

# If the content of the target file correct
def test_target_file_content():
    """Test that target.py contains the expected test function."""
    target_path = Path("/app/task_dir/target.py")
    
    actual_content = target_path.read_text().strip()
    
    expected_content = """def test(a):
    return a"""
    
    assert actual_content == expected_content, (
        f"Expected content:\n{expected_content}\n\nBut got:\n{actual_content}"
    )
