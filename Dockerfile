# Dockerfile
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS base

# 1. Install native C/C++ geospatial & HDF5/vsicurl libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    gdal-bin \
    libgdal-dev \
    libhdf5-dev \
    libspatialindex-dev \
    libgeos-dev \
    libproj-dev \
    curl \
    ca-certificates \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 2. Tune GDAL / VSICURL for high-speed NASA Earthdata S3 byte-range streaming
ENV GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR" \
    CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".h5,.tif,.tiff,.vrt" \
    CPL_VSIL_CURL_CHUNK_SIZE="10485760" \
    GDAL_HTTP_MULTIRANGE="YES" \
    GDAL_HTTP_MERGE_CONSECUTIVE_RANGES="YES" \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH="/app"

WORKDIR /app

# 3. Install Python dependencies into isolated /app/.venv
COPY pyproject.toml ./
RUN uv venv /app/.venv && \
    . /app/.venv/bin/activate && \
    uv pip install \
    fastapi[standard] \
    uvicorn[standard] \
    langgraph \
    langchain \
    langchain-anthropic \
    langchain-community \
    langchain-mcp-adapters \
    fastmcp \
    earthengine-api \
    earthaccess \
    asf_search \
    rioxarray \
    xarray \
    zarr \
    rasterio \
    numpy \
    pillow \
    google-cloud-storage \
    pydantic \
    httpx

ENV PATH="/app/.venv/bin:$PATH"

# 4. Copy application source code
COPY gee_math/ ./gee_math/
COPY mcp_servers/ ./mcp_servers/
COPY agents/ ./agents/
COPY scripts/ ./scripts/
COPY static/ ./static/
COPY app.py ./

# Create persistent cache & credential mount directories
RUN mkdir -p /app/local_cache/antioquia_aburra /root/.config/earthengine

EXPOSE 8000 8001 8002
