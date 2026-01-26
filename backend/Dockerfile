FROM python:3.10-slim

# Prevent Python from writing .pyc files
ENV PYTHONDONTWRITEBYTECODE=1
# Make output appear in logs immediately
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies required by TensorFlow and image processing
RUN apt-get update && apt-get install -y --no-install-recommends \
     build-essential \
     libglib2.0-0 \
     libsm6 \
     libxext6 \
     libxrender-dev \
     libmagic1 \
     curl \
     && rm -rf /var/lib/apt/lists/* \
     && apt-get clean

# Create non-root user for security
RUN groupadd -r appgroup && useradd -r -g appgroup appuser

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create uploads directory and set permissions
RUN mkdir -p /app/backend/uploads \
     && chown -R appuser:appgroup /app

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8000

# Start the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]