FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install the CPU-only torch wheel first. sentence-transformers depends on torch, but
# the default PyPI wheel bundles CUDA libraries that are never used on Render (no GPU)
# and blow past the 512MB free-tier memory limit just on import. Installing the
# CPU-only build here satisfies that dependency before requirements.txt would otherwise
# pull in the much larger GPU-enabled default.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application backend code
COPY backend /app/backend

# Copy the static dashboard so FastAPI can serve it from the same process/port -
# Render only routes traffic to one port per service, so a separate Node server
# for the frontend can't be reached externally alongside the API.
COPY frontend1/ada-desk /app/frontend

# Set environment variables
ENV PYTHONPATH=/app/backend
ENV HOST=0.0.0.0
ENV PORT=8000

# Keep thread pools small - each OpenMP/tokenizer thread adds its own memory
# overhead, which matters on a 512MB instance.
ENV OMP_NUM_THREADS=1
ENV TOKENIZERS_PARALLELISM=false

EXPOSE 8000

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]

