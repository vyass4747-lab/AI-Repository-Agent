FROM python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY . .
RUN pip install --upgrade pip && pip install uv && uv sync --no-dev
ENV PATH="/app/.venv/bin:$PATH"
CMD ["uvicorn", "ai_repository_agent.app:app", "--host", "0.0.0.0", "--port", "8000"]
