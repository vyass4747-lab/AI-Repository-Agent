import re
from contextvars import ContextVar
from pathlib import Path

from langchain.tools import tool


DEFAULT_PROJECT_ROOT = Path(__file__).resolve().parents[3]
PROJECT_ROOT: ContextVar[Path] = ContextVar(
    "repository_project_root",
    default=DEFAULT_PROJECT_ROOT,
)


def set_repository_root(root: Path):
    """Set the repository root for the current request."""
    return PROJECT_ROOT.set(root.resolve())


def reset_repository_root(token) -> None:
    PROJECT_ROOT.reset(token)

IGNORED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
}

TEXT_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".kt", ".cs", ".go",
    ".rs", ".rb", ".php", ".html", ".css", ".scss", ".json", ".yaml",
    ".yml", ".toml", ".ini", ".cfg", ".conf", ".md", ".txt", ".sql",
    ".sh", ".bash", ".ps1", ".c", ".cpp", ".h", ".hpp", ".vue",
    ".svelte", ".xml", ".gradle",
}


@tool
def list_repository_tool() -> str:
    """
    List all files in the current repository.
    Exclude unnecessary directories and sensitive .env files.

    """

    root = PROJECT_ROOT.get()
    files = []
    for path in root.rglob("*"):

        if any(part in IGNORED_DIRS for part in path.parts):
            continue

        if (
            path.is_file()
            and path.name != ".env"
            and not path.name.startswith(".env.")
        ):
            files.append(str(path.relative_to(root)))


    return "\n".join(sorted(files)) if files else "No files found"





@tool
def read_file(file_path: str) -> str:
    """Read a file safely from the current repository."""

    try:
        root = PROJECT_ROOT.get()
        resolved_path = (root / file_path).resolve()

        # Ensure the path stays inside the repository
        resolved_path.relative_to(root.resolve())

        # Reject sensitive files
        if resolved_path.name == ".env" or resolved_path.name.startswith(".env."):
            return "Access denied: Sensitive file."

        # Check file existence and type
        if not resolved_path.exists():
            return "Error: File does not exist."

        if not resolved_path.is_file():
            return "Error: Path is not a file."

        # Limit file size to 1 MB
        if resolved_path.stat().st_size > 1_000_000:
            return "Error: File is too large."

        # Read file content
        with open(resolved_path, "r", encoding="utf-8") as f:
            return f.read()

    except ValueError:
        return "Access denied: File is outside the repository."
    except (OSError, UnicodeDecodeError):
        return "Error: Could not read this file."


@tool
def search_repository(query: str, max_results: int = 60) -> str:
    """Search text files in the repository for a keyword or regular expression."""
    try:
        pattern = re.compile(query, re.IGNORECASE)
    except re.error:
        pattern = re.compile(re.escape(query), re.IGNORECASE)

    root = PROJECT_ROOT.get()
    matches = []
    for path in root.rglob("*"):
        if not path.is_file() or any(part in IGNORED_DIRS for part in path.parts):
            continue
        if path.suffix.lower() not in TEXT_EXTENSIONS or path.name.startswith(".env"):
            continue

        try:
            if path.stat().st_size > 1_000_000:
                continue
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue

        for line_number, line in enumerate(lines, start=1):
            if pattern.search(line):
                relative = path.relative_to(root).as_posix()
                matches.append(f"{relative}:{line_number}:{line.strip()}")
                if len(matches) >= max_results:
                    return "\n".join(matches)

    return "\n".join(matches) if matches else "No matches found."
