ARG PYTHON_VERSION=3.13-bookworm
ARG SLIM_PYTHON_VERSION=3.13-slim-bookworm

# ---------- builder ----------
FROM python:${PYTHON_VERSION} AS builder

# Pin uv for reproducible builds (tag or digest); copy static binaries.
# See: https://docs.astral.sh/uv/guides/integration/docker/#installing-uv
COPY --from=ghcr.io/astral-sh/uv:0.8.12 /uv /uvx /usr/local/bin/

WORKDIR /app
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    HF_HOME=/opt/hf-cache \
    XDG_CACHE_HOME=/tmp

# 1) Install deps (no project). Copy only lock + pyproject to keep this layer warm.
COPY pyproject.toml fastmcp.json uv.lock ./
RUN uv sync --locked --no-cache --no-install-project --no-editable --extra drivers

# 2) Add source and perform final sync to install the project (non-editable) into .venv
COPY src/ ./src/
COPY scripts/prefetch_embeddings.py ./scripts/prefetch_embeddings.py
RUN uv sync --locked --no-cache --no-editable --extra drivers
RUN uv pip install --no-cache --no-deps --no-build-isolation .

# 3) Prefetch the default embedding model into the image cache
RUN mkdir -p /opt/hf-cache \
 && uv run python /app/scripts/prefetch_embeddings.py


# ---------- runtime ----------
FROM python:${SLIM_PYTHON_VERSION} AS runtime
WORKDIR /app

# Also provide uv binaries in runtime for healthcheck and tooling
COPY --from=ghcr.io/astral-sh/uv:0.8.12 /uv /uvx /usr/local/bin/

# Create dedicated user (no shell, no home write) and copy only the ready venv + needed files
RUN groupadd --system app && useradd --system --gid app --home /app --shell /usr/sbin/nologin app
RUN mkdir -p /app/scripts

## Install runtime shared libraries for all supported DBs
RUN set -eux; \
    apt-get update; \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    unixodbc \
    libpq5 \
    libmariadb3 \
    curl \
    gnupg \
    ; \
    rm -rf /var/lib/apt/lists/*

# Install Microsoft ODBC Driver for SQL Server
RUN set -eux; \
    curl -sSL -O https://packages.microsoft.com/config/debian/$(grep VERSION_ID /etc/os-release | cut -d '"' -f 2 | cut -d '.' -f 1)/packages-microsoft-prod.deb ; \
    dpkg -i packages-microsoft-prod.deb ; \
    rm packages-microsoft-prod.deb ; \
    apt-get update ; \
    DEBIAN_FRONTEND=noninteractive ACCEPT_EULA=Y apt-get install -y msodbcsql18 ; \
    rm -rf /var/lib/apt/lists/*

# Bring over the built virtualenv and application sources; keep ownership minimal
COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --from=builder --chown=app:app /opt/hf-cache /opt/hf-cache
COPY --chown=app:app fastmcp.json /app/fastmcp.json
COPY --chown=app:app src/ /app/src/
COPY --chown=app:app scripts/healthcheck.py /app/scripts/healthcheck.py

# Prefer venv shims first; avoid runtime bytecode writes and ensure unbuffered logs
ENV PATH="/app/.venv/bin:$PATH" \
    UV_CACHE_DIR="/tmp/uv-cache" \
    XDG_CACHE_HOME="/tmp" \
    HF_HOME="/opt/hf-cache" \
    NL2SQL_MCP_EMBEDDING_MODEL="minishlab/potion-base-8M" \
    PYTHONPATH="/app/src:${PYTHONPATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

USER app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 CMD uv run python /app/scripts/healthcheck.py || exit 1

ENTRYPOINT ["fastmcp", "run"]
CMD ["--transport", "http", "--host", "0.0.0.0", "--port", "8000"]
