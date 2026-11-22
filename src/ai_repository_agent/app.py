import shutil
import subprocess
import tempfile
import uuid
import zipfile
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from ai_repository_agent.workflow import run_repository_agent


app = FastAPI(
    title="AI Repository Agent",
    description="Repository-grounded bug analysis and fix suggestions",
)

sessions: dict[str, dict] = {}
ALLOWED_REPOSITORY_HOSTS = {"github.com", "gitlab.com", "bitbucket.org"}


class RepositoryRequest(BaseModel):
    repository_url: str


class ChatRequest(BaseModel):
    message: str


def validate_repository_url(repository_url: str) -> str:
    value = repository_url.strip()
    parsed = urlparse(value)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_REPOSITORY_HOSTS:
        raise HTTPException(
            status_code=400,
            detail="Use an HTTPS repository URL from GitHub, GitLab, or Bitbucket.",
        )
    if parsed.username or parsed.password:
        raise HTTPException(
            status_code=400,
            detail="Repository credentials must not be included in the URL.",
        )
    return value


def create_session_root() -> Path:
    return Path(tempfile.mkdtemp(prefix="repo-agent-"))


@app.post("/api/sessions/url")
def load_repository_from_url(request: RepositoryRequest):
    repository_url = validate_repository_url(request.repository_url)
    session_id = str(uuid.uuid4())
    root = create_session_root()

    try:
        result = subprocess.run(
            ["git", "clone", "--depth", "1", repository_url, str(root / "repository")],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if result.returncode != 0:
            shutil.rmtree(root, ignore_errors=True)
            raise HTTPException(
                status_code=400,
                detail=f"Could not clone repository: {result.stderr.strip()[:500]}",
            )
    except FileNotFoundError:
        shutil.rmtree(root, ignore_errors=True)
        raise HTTPException(status_code=500, detail="Git is not available on the server.")
    except subprocess.TimeoutExpired:
        shutil.rmtree(root, ignore_errors=True)
        raise HTTPException(status_code=504, detail="Repository clone timed out.")

    repository_root = root / "repository"
    sessions[session_id] = {
        "repository_root": repository_root,
        "repository_name": repository_url.rstrip("/").split("/")[-1],
        "messages": [],
    }
    return {"session_id": session_id, "repository_name": repository_url}


@app.post("/api/sessions/upload")
async def load_repository_from_zip(
    archive: UploadFile = File(...),
    repository_name: str = Form("uploaded-repository"),
):
    if not archive.filename or not archive.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Upload a .zip repository archive.")

    session_id = str(uuid.uuid4())
    root = create_session_root()
    zip_path = root / "uploaded.zip"
    repository_root = root / "repository"
    repository_root.mkdir()

    content = await archive.read()
    if len(content) > 100_000_000:
        shutil.rmtree(root, ignore_errors=True)
        raise HTTPException(status_code=413, detail="Archive exceeds the 100 MB limit.")
    zip_path.write_bytes(content)

    try:
        with zipfile.ZipFile(zip_path) as uploaded_zip:
            for member in uploaded_zip.infolist():
                target = (repository_root / member.filename).resolve()
                target.relative_to(repository_root.resolve())
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with uploaded_zip.open(member) as source, open(target, "wb") as destination:
                        shutil.copyfileobj(source, destination)
    except (zipfile.BadZipFile, ValueError):
        shutil.rmtree(root, ignore_errors=True)
        raise HTTPException(status_code=400, detail="The uploaded file is not a valid zip archive.")

    sessions[session_id] = {
        "repository_root": repository_root,
        "repository_name": repository_name,
        "messages": [],
    }
    return {"session_id": session_id, "repository_name": repository_name}


@app.post("/api/sessions/{session_id}/chat")
def chat(session_id: str, request: ChatRequest):
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Repository session not found.")
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    result = run_repository_agent(message, session["repository_root"])
    response = {
        "answer": result.get("analysis", "No analysis produced."),
        "relevant_files": [
            path for path in result.get("relevant_files", "").splitlines() if path
        ],
        "selection_error": result.get("selection_error", ""),
    }
    session["messages"].append({"role": "user", "content": message})
    session["messages"].append({"role": "assistant", "content": response})
    return response


@app.get("/api/sessions/{session_id}")
def get_session(session_id: str):
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Repository session not found.")
    return {
        "repository_name": session["repository_name"],
        "messages": session["messages"],
    }


@app.delete("/api/sessions/{session_id}")
def delete_session(session_id: str):
    session = sessions.pop(session_id, None)
    if not session:
        raise HTTPException(status_code=404, detail="Repository session not found.")
    root = session["repository_root"]
    shutil.rmtree(root.parent, ignore_errors=True)
    return {"status": "deleted"}


@app.get("/", response_class=HTMLResponse)
def index():
    return HTMLResponse(WEB_UI)


@app.get("/health")
def health():
    return {"status": "ok"}


WEB_UI = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AI Repository Agent</title>
  <style>
    :root { color-scheme: dark; --bg:#0b1020; --panel:#141b2d; --muted:#9aa8c7; --accent:#7c9cff; }
    * { box-sizing:border-box; } body { margin:0; background:var(--bg); color:#edf2ff; font-family:Inter,system-ui,sans-serif; }
    .shell { min-height:100vh; display:grid; grid-template-columns:320px 1fr; }
    aside { border-right:1px solid #263250; padding:24px; background:#101729; }
    main { display:flex; flex-direction:column; height:100vh; }
    h1 { margin:0 0 8px; font-size:22px; } .muted { color:var(--muted); font-size:14px; }
    label { display:block; margin-top:18px; margin-bottom:8px; font-weight:600; }
    input, button { width:100%; border-radius:8px; border:1px solid #344160; background:#192238; color:white; padding:11px 12px; }
    button { cursor:pointer; background:var(--accent); color:#09101f; border:0; font-weight:700; margin-top:10px; }
    button:disabled { opacity:.55; cursor:not-allowed; }
    #messages { flex:1; overflow:auto; padding:28px max(28px, 8vw); }
    .message { max-width:900px; margin:0 auto 18px; padding:16px 18px; border-radius:12px; white-space:pre-wrap; line-height:1.55; }
    .user { background:#253252; margin-left:20%; } .assistant { background:var(--panel); margin-right:8%; }
    .files { color:#b9c6e6; font-size:13px; margin-top:10px; }
    .composer { display:flex; gap:10px; padding:18px max(28px, 8vw); border-top:1px solid #263250; }
    .composer input { flex:1; } .composer button { width:110px; margin:0; }
    .divider { margin:18px 0; border-top:1px solid #263250; }
  </style>
</head>
<body>
<div class="shell">
  <aside>
    <h1>AI Repository Agent</h1>
    <div class="muted">Repository-grounded debugging</div>
    <label for="url">Repository URL</label>
    <input id="url" placeholder="https://github.com/org/repo">
    <button id="loadUrl">Load repository</button>
    <div class="divider"></div>
    <label for="zip">Or upload ZIP</label>
    <input id="zip" type="file" accept=".zip">
    <button id="loadZip">Upload ZIP</button>
    <div id="status" class="muted" style="margin-top:14px"></div>
  </aside>
  <main>
    <div id="messages"></div>
    <form id="chatForm" class="composer">
      <input id="question" placeholder="Ask about a bug, auth failure, architecture, or fix..." autocomplete="off">
      <button type="submit">Analyze</button>
    </form>
  </main>
</div>
<script>
let sessionId = null;
const status = document.querySelector('#status');
const messages = document.querySelector('#messages');
function addMessage(role, content, files = []) {
  const div = document.createElement('div');
  div.className = `message ${role}`;
  div.textContent = content;
  if (files.length) {
    const list = document.createElement('div');
    list.className = 'files';
    list.textContent = 'Relevant files: ' + files.join(', ');
    div.appendChild(list);
  }
  messages.appendChild(div);
  messages.scrollTop = messages.scrollHeight;
}
document.querySelector('#loadUrl').onclick = async () => {
  const url = document.querySelector('#url').value.trim();
  if (!url) return;
  status.textContent = 'Cloning repository...';
  const response = await fetch('/api/sessions/url', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({repository_url:url})});
  const data = await response.json();
  if (!response.ok) { status.textContent = data.detail; return; }
  sessionId = data.session_id;
  messages.innerHTML = '';
  status.textContent = `Loaded ${data.repository_name}`;
};
document.querySelector('#loadZip').onclick = async () => {
  const file = document.querySelector('#zip').files[0];
  if (!file) return;
  status.textContent = 'Uploading repository...';
  const form = new FormData();
  form.append('archive', file);
  form.append('repository_name', file.name);
  const response = await fetch('/api/sessions/upload', {method:'POST', body:form});
  const data = await response.json();
  if (!response.ok) { status.textContent = data.detail; return; }
  sessionId = data.session_id;
  messages.innerHTML = '';
  status.textContent = `Loaded ${data.repository_name}`;
};
document.querySelector('#chatForm').addEventListener('submit', async (event) => {
  event.preventDefault();
  if (!sessionId) { status.textContent = 'Load a repository first.'; return; }
  const input = document.querySelector('#question');
  const message = input.value.trim();
  if (!message) return;
  input.value = '';
  addMessage('user', message);
  status.textContent = 'Investigating repository...';
  const response = await fetch(`/api/sessions/${sessionId}/chat`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({message})});
  const data = await response.json();
  status.textContent = 'Analysis complete';
  if (!response.ok) addMessage('assistant', data.detail);
  else addMessage('assistant', data.answer, data.relevant_files);
});
</script>
</body>
</html>"""
