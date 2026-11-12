# API + interface do hospital-siting (Fase 2). A gold vem do PostGIS (docker-compose.deploy.yml).
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PYTHONUNBUFFERED=1 \
    HS_DOCS_DIR=/app/docs

WORKDIR /app

# Dependências primeiro (camada em cache enquanto pyproject/uv.lock não mudam).
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
COPY config ./config
COPY docs/como-funciona ./docs/como-funciona
RUN uv sync --frozen --no-dev

RUN useradd --create-home --uid 1000 app
USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/saude', timeout=4)"

CMD ["/app/.venv/bin/uvicorn", "hospital_siting.api.app:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
