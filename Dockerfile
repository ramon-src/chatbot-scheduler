# =============================================================================
# SIMPLIFICAPSI - DOCKERFILE
# =============================================================================

# =============================================================================
# STAGE 1: Base Python Image with uv
# =============================================================================
FROM python:3.11-slim as base

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install uv

# =============================================================================
# STAGE 2: Dependencies
# =============================================================================
FROM base as dependencies

# Set working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies with uv (without local package)
RUN uv sync --frozen --no-dev --no-install-project

# =============================================================================
# STAGE 3: Development
# =============================================================================
FROM dependencies as development

# Copy source code (including README.md)
COPY . .

# Install development dependencies (including local package)
RUN uv sync --frozen

# Create logs directory
RUN mkdir -p logs

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Default command
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# =============================================================================
# STAGE 4: Production
# =============================================================================
FROM dependencies as production

# Create non-root user
RUN groupadd -r simplificapsi && useradd -r -g simplificapsi simplificapsi

# Copy source code (including README.md)
COPY . .

# Install production dependencies (including local package)
RUN uv sync --frozen --no-dev

# Create necessary directories
RUN mkdir -p logs && \
    chown -R simplificapsi:simplificapsi /app

# Switch to non-root user
USER simplificapsi

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Default command
CMD ["uv", "run", "gunicorn", "app.main:app", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000"]
