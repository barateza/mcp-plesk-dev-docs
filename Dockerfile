# Use python:3.12-slim as the base image for a small production footprint
FROM python:3.12-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # uv optimizations
    UV_COMPILE_BYTECODE=1 \
    # Hugging Face cache location - requirements specified this path
    HF_HOME=/app/.cache/huggingface \
    # Ensure the virtual environment created by uv is used
    PATH="/app/.venv/bin:$PATH"

# Install system dependencies
# libgomp1: OpenMP runtime, required by many ML/scientific libraries (torch, numpy, tantivy, lancedb)
# ca-certificates: Required for SSL/TLS connections (e.g., downloading models from Hugging Face)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy uv binary from the official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Create a non-root user for security
RUN useradd -m -u 1000 mcpuser

# Set working directory and set ownership
WORKDIR /app
RUN chown mcpuser:mcpuser /app

# Switch to the non-root user
USER mcpuser

# Copy dependency files to optimize layer caching.
# We use a wildcard for uv.lock in case it hasn't been generated or committed yet.
# This ensures the build doesn't fail if uv.lock is missing, while still
# utilizing it for layer caching if it exists.
COPY --chown=mcpuser:mcpuser pyproject.toml uv.lock* ./

# Install dependencies
# --no-install-project avoids installing the local package at this stage,
# allowing Docker to cache this layer even if application source code changes.
RUN uv sync --no-install-project --no-dev

# Copy the rest of the application code
COPY --chown=mcpuser:mcpuser . .

# Install the project itself (this also compiles the bytecodes due to UV_COMPILE_BYTECODE)
RUN uv sync --no-dev

# Ensure necessary directories exist for model cache and storage
RUN mkdir -p /app/.cache/huggingface /app/storage

# Expose port 8000 (specified in requirements)
# This is typically used for SSE (Server-Sent Events) transport
EXPOSE 8000

# Set the entrypoint to run the MCP server using the human-facing package
# name. The `mcp_plesk_dev_docs` package is a compatibility shim mapping to
# the internal `mcp_plesk_dev_docs` package so this is non-breaking.
ENTRYPOINT ["python", "-m", "mcp_plesk_dev_docs.server"]
