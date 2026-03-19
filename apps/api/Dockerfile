FROM python:3.11-slim

WORKDIR /app

# Install system deps for PDF parsing + PostgreSQL
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY apps/api/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

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
