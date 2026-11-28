# Multi-stage hardened Backend image (FastAPI + ARQ Worker + pre-installed DuckDB httpfs)
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Pre-install DuckDB httpfs extension into a dedicated home directory so runtime
# never needs network access or writable system paths.
RUN mkdir -p /opt/duckdb-home \
    && HOME=/opt/duckdb-home python -c "import duckdb; conn = duckdb.connect(':memory:'); conn.execute('INSTALL httpfs'); conn.execute('LOAD httpfs'); conn.close()"


FROM python:3.12-slim AS runner

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    HOME=/home/appuser \
    PYTHONPATH=/app/backend

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system appuser \
    && useradd --system --gid appuser --create-home --home-dir /home/appuser appuser

COPY --from=builder /opt/venv /opt/venv
COPY --from=builder --chown=appuser:appuser /opt/duckdb-home/.duckdb /home/appuser/.duckdb
COPY --chown=appuser:appuser backend ./backend

RUN mkdir -p /app/data/documents && chown -R appuser:appuser /app/data

USER appuser

# Prove non-root DuckDB LOAD httpfs works offline with auto-install disabled.
RUN python -c "import duckdb; conn = duckdb.connect(':memory:'); conn.execute('SET autoinstall_known_extensions=false'); conn.execute('LOAD httpfs'); conn.close()"

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD ["curl", "-fsS", "http://127.0.0.1:8000/health"]

CMD ["python", "-m", "uvicorn", "app.main:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "8000"]
