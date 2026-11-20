from pathlib import Path
from langchain.tools import tool


PROJECT_ROOT = Path(__file__).resolve().parents[3]

IGNORED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
}


@tool
def list_repository_tool() -> str:
    """
    List all files in the current repository.
    Exclude unnecessary directories and sensitive .env files.

    """

    files = []

    for path in PROJECT_ROOT.rglob("*"):

        if any(part in IGNORED_DIRS for part in path.parts):
            continue

        if path.is_file() and path.name != ".env":
            files.append(str(path.relative_to(PROJECT_ROOT)))


    return "\n".join(sorted(files)) if files else "No files found"





@tool
def read_file(file_path: str) -> str:
    """Read a file safely from the current repository."""

    try:
        resolved_path = (PROJECT_ROOT / file_path).resolve()

        # Ensure the path stays inside the repository
        resolved_path.relative_to(PROJECT_ROOT.resolve())

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
