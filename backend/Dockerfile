# Backend FastAPI Container
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p configs data/clients

# Environment variables (will be overridden by docker-compose or ECS)
ENV USE_POSTGRES=true
ENV POSTGRES_HOST=localhost
ENV POSTGRES_PORT=5432
ENV POSTGRES_DB=beansco_main
ENV POSTGRES_USER=beansco
ENV POSTGRES_PASSWORD=changeme123

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health')" || exit 1

# Run backend
CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000"]
