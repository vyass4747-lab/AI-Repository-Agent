from ai_repository_agent.tools.filesyatem import list_repository_tool, read_file


def test_list_repository_excludes_environment_files():
    files = list_repository_tool.invoke({})

    assert ".env" not in files
    assert ".env.example" not in files


def test_read_file_rejects_outside_repository():
    result = read_file.invoke({"file_path": "../outside.txt"})

    assert "outside the repository" in result
