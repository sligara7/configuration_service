# Configuration Service (SVC-004) Docker Image
#
# Uses UV for fast, reproducible dependency installation.
#
# Usage:
#   docker build -t bluesky-configuration-service .
#   docker run -it --rm -p 8004:8004 bluesky-configuration-service

FROM python:3.11-slim AS builder

# Install UV
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Install dependencies first (layer caching — only re-runs when pyproject.toml changes)
COPY pyproject.toml README.md ./
RUN uv pip install --system --no-cache .

# Production stage
FROM python:3.11-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application source
COPY src/ ./src/

# Create non-root user
RUN useradd -m -u 1000 configservice && \
    chown -R configservice:configservice /app

USER configservice

EXPOSE 8004

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8004/health', timeout=5.0)"

CMD ["python", "-m", "uvicorn", "configuration_service.main:app", "--host", "0.0.0.0", "--port", "8004"]
