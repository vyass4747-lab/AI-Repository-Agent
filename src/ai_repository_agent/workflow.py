import json
import re
from typing import TypedDict

from langgraph.graph import StateGraph, START, END
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage

from ai_repository_agent.config import GROQ_API_KEY
from ai_repository_agent.tools.filesyatem import (
    list_repository_tool,
    read_file,
    search_repository,
    set_repository_root,
    reset_repository_root,
)
from pathlib import Path


class RepoState(TypedDict):
    user_request: str
    repository_files: str
    relevant_files: str
    repository_context: str
    analysis: str
    selection_error: str
    repository_root: str


def explore_repository(state:RepoState)->dict:
    set_repository_root(Path(state.get("repository_root", ".")))
    files = list_repository_tool.invoke({})
    return {"repository_files": files}


def _keywords(request: str) -> list[str]:
    stop_words = {
        "why", "where", "what", "which", "please", "find", "fix", "the",
        "for", "and", "with", "from", "this", "that", "is", "are", "has",
        "have", "does", "my", "our", "user", "please", "issue", "problem",
        "error", "bug", "repository", "repo",
    }
    words = re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", request.lower())
    return list(dict.fromkeys(word for word in words if word not in stop_words))


def _fallback_relevant_files(repository_files: str, request: str) -> list[str]:
    files = [line for line in repository_files.splitlines() if line]
    keywords = _keywords(request)

    ranked = []
    for file_path in files:
        low_path = file_path.lower()
        score = sum(4 for keyword in keywords if keyword in low_path)
        for keyword in keywords:
            if not keyword:
                continue
            search_result = search_repository.invoke({
                "query": re.escape(keyword),
                "max_results": 3,
            })
            if search_result != "No matches found." and file_path in search_result:
                score += 3
        ranked.append((score, file_path))

    ranked.sort(key=lambda item: (-item[0], item[1]))
    selected = [file_path for score, file_path in ranked if score > 0][:12]
    if not selected:
        selected = [
            file_path for file_path in files
            if file_path.lower().endswith((".py", ".js", ".ts", ".tsx", ".java", ".go"))
        ][:12]
    return selected


def _extract_json_file_list(content: str) -> list[str]:
    cleaned = content.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, str)]


def select_relevant_files(state: RepoState) -> dict:
    set_repository_root(Path(state.get("repository_root", ".")))
    files = state.get("repository_files", "")
    fallback = _fallback_relevant_files(files, state["user_request"])

    if not GROQ_API_KEY:
        return {
            "relevant_files": "\n".join(fallback),
            "selection_error": "GROQ_API_KEY is not configured; used repository keyword matching.",
        }

    llm = ChatGroq(
        model="openai/gpt-oss-20b",
        api_key=GROQ_API_KEY,
        temperature=0,
    )
    prompt = (
        "Select the repository files most likely to contain the answer to the "
        "developer request. Return only a JSON array of relative file paths. "
        "Do not include explanations.\n\n"
        f"Developer request:\n{state['user_request']}\n\n"
        f"Repository files:\n{files}"
    )
    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        selected = _extract_json_file_list(
            response.content if isinstance(response.content, str) else str(response.content)
        )
        available = set(files.splitlines())
        selected = [path for path in selected if path in available][:12]
    except Exception as exc:
        selected = []
        selection_error = f"LLM file selection failed: {exc}; used repository keyword matching."
    else:
        selection_error = ""

    return {
        "relevant_files": "\n".join(selected or fallback),
        "selection_error": selection_error,
    }


def read_relevant_context(state: RepoState) -> dict:
    set_repository_root(Path(state.get("repository_root", ".")))
    file_paths = [
        path for path in state.get("relevant_files", "").splitlines() if path
    ]
    chunks = []
    total_chars = 0

    for file_path in file_paths:
        content = read_file.invoke({"file_path": file_path})
        if content.startswith("Error:") or content.startswith("Access denied:"):
            continue
        chunk = f"\n\n===== {file_path} =====\n{content}"
        if total_chars + len(chunk) > 180_000:
            remaining = 180_000 - total_chars
            if remaining > 500:
                chunks.append(chunk[:remaining])
            break
        chunks.append(chunk)
        total_chars += len(chunk)

    return {"repository_context": "".join(chunks)}


def analyze_repository(state: RepoState) -> dict:
    set_repository_root(Path(state.get("repository_root", ".")))
    if not GROQ_API_KEY:
        return {
            "analysis": (
                "GROQ_API_KEY is not configured. Set it in .env, then run the "
                "agent again.\n\n"
                f"Relevant files identified:\n{state.get('relevant_files', '')}"
            )
        }

    llm = ChatGroq(
        model="openai/gpt-oss-20b",
        api_key=GROQ_API_KEY,
        temperature=0,
    )
    system_prompt = (
        "You are a senior repository debugging agent. Investigate only from "
        "the supplied repository context. Identify the exact likely file and "
        "line or function names, explain the root cause, and propose a concrete "
        "fix. If evidence is insufficient, say what to verify and never invent "
        "file names or behavior."
    )
    human_prompt = (
        f"User request:\n{state['user_request']}\n\n"
        f"Relevant files:\n{state.get('relevant_files', '')}\n\n"
        f"Repository context:\n{state.get('repository_context', '')}"
    )
    try:
        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=human_prompt),
        ])
        content = response.content if isinstance(response.content, str) else str(response.content)
    except Exception as exc:
        content = f"The repository analysis could not be completed: {exc}"
    return {"analysis": content}


graph = StateGraph(RepoState)

graph.add_node("explore_repository",explore_repository)
graph.add_node("select_relevant_files", select_relevant_files)
graph.add_node("read_relevant_context", read_relevant_context)
graph.add_node("analyze_repository", analyze_repository)
graph.add_edge(START,"explore_repository")
graph.add_edge("explore_repository","select_relevant_files")
graph.add_edge("select_relevant_files","read_relevant_context")
graph.add_edge("read_relevant_context","analyze_repository")
graph.add_edge("analyze_repository",END)

workflow = graph.compile()


def run_repository_agent(user_request: str, repository_root: Path) -> dict:
    """Run an analysis with repository_root isolated for this request."""
    root = repository_root.resolve()
    token = set_repository_root(root)
    try:
        return workflow.invoke({
            "user_request": user_request,
            "repository_root": str(root),
            "repository_files": "",
            "relevant_files": "",
            "repository_context": "",
            "analysis": "",
            "selection_error": "",
        })
    finally:
        reset_repository_root(token)