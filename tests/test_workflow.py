from ai_repository_agent.workflow import workflow


def test_workflow_identifies_relevant_files_and_reports_analysis():
    result = workflow.invoke({
        "user_request": "why is authentication failing",
        "repository_files": "",
        "relevant_files": "",
        "repository_context": "",
        "analysis": "",
        "selection_error": "",
    })

    assert result["relevant_files"]
    assert result["analysis"]
