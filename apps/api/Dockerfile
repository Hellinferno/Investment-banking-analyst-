FROM python:3.11-slim

WORKDIR /app

# Install runtime deps for OCR and numerical wheels. The database driver and
# document libraries are installed from binary wheels and need no compiler.
RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    fonts-dejavu-core \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY apps/api/requirements.txt ./requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --timeout 120 --retries 10 -r requirements.txt

# Copy application source
COPY apps/api/src/ ./src/
COPY apps/api/alembic/ ./alembic/
COPY apps/api/alembic.ini ./alembic.ini

# Create data directories
RUN mkdir -p /app/data/uploads /app/data/outputs

# Expose API port
EXPOSE 8000

# Run migrations then start server
CMD ["sh", "-c", "cd /app && python -m alembic upgrade head && uvicorn src.main:app --host 0.0.0.0 --port 8000"]
