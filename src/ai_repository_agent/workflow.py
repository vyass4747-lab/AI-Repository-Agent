from typing import TypedDict

from langgraph.graph import StateGraph , START , END

from src.ai_repository_agent.tools.filesyatem import list_repository_tool


class RepoState(TypedDict):

    user_request:str
    repository_files:str


def explore_repository(state:RepoState)->dict:
    files = list_repository_tool.invoke({})

    return {
        "repository files":files
    }


graph = StateGraph(RepoState)

graph.add_node("explore_repository",explore_repository)
graph.add_edge(START,explore_repository)
graph.add_edge(explore_repository,END)

workflow = graph.compile()