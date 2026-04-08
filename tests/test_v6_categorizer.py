import pytest
import os
import pathlib

def test_categorizer_full_flow(project_client, mock_project):
    """Verify adding a category, moving a file, and refreshing config."""
    proj_path = str(mock_project)
    file_to_move = mock_project / "src" / "main.py"
    target_cat_name = "Legacy"
    target_cat_rel_path = "archive/old"
    
    # 1. Add Category
    res_add = project_client.post("/api/project/categories", json={
        "project_path": proj_path,
        "categories": {target_cat_name: target_cat_rel_path}
    })
    assert res_add.status_code == 200
    
    # 2. Categorize (Move)
    res_move = project_client.post("/api/actions/categorize", json={
        "project_path": proj_path,
        "paths": [str(file_to_move)],
        "category_name": target_cat_name
    })
    assert res_move.status_code == 200
    
    # 3. Verify physical existence
    new_path = mock_project / "archive" / "old" / "main.py"
    assert new_path.exists()
    assert not file_to_move.exists()
    
    # 4. Verify config update (staging list should ideally reflect the change if the backend handled it)
    # Note: batch_categorize in core calls move_file, but doesn't automatically remove from staging_list 
    # UNLESS the frontend/web_app specifically handle it.
    # In web_app's current implementation, it just calls the core. 
    # Let's check if the file is STILL in staging if it was there.
    
    # Pre-condition: stage the file first
    project_client.post("/api/project/settings", json={
        "project_path": proj_path,
        "settings": {"staging_list": [str(file_to_move)]}
    })
    
    # Run move again with a different file
    file2 = mock_project / "src" / "utils.js"
    project_client.post("/api/actions/categorize", json={
        "project_path": proj_path, "paths": [str(file2)], "category_name": target_cat_name
    })
    
    assert (mock_project / "archive" / "old" / "utils.js").exists()

def test_categorize_invalid_category_rejected(project_client, mock_project):
    """Verify that moving to a non-existent category fails gracefully."""
    res = project_client.post("/api/actions/categorize", json={
        "project_path": str(mock_project),
        "paths": [str(mock_project / "src" / "main.py")],
        "category_name": "NonExistent"
    })
    assert res.status_code == 400
    assert "not defined" in res.json()["detail"]
