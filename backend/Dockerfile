FROM python:3.11-slim

WORKDIR /app

# System dependencies
# - curl: used by health checks
# - libmagic1: required by python-magic (file type validation)
# - libsqlite3-dev: required by chromadb
RUN apt-get update && apt-get install -y --no-install-recommends \
     curl \
     libmagic1 \
     libsqlite3-dev \
     && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (layer cached unless requirements.txt changes)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy Alembic config and migrations
COPY alembic.ini .
COPY alembic/ ./alembic/

# Copy application source code
COPY app/ ./app/

# Copy the trained ML model
# The model file must exist at backend/model/tumor_model.keras on your machine
COPY model/ ./model/

# Copy medical knowledge base for RAG ingestion
COPY data/medical_docs /app/data/medical_docs

# Environment variables
ENV CHROMA_DIR=/app/data/chroma_db
ENV MEDICAL_DOCS_DIR=/app/data/medical_docs
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]