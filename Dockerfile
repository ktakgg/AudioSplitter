FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY pyproject.toml uv.lock ./
RUN pip install uv && uv pip install --system --no-cache -r pyproject.toml

# Copy application code
COPY . .

# Set environment variables for deployment
ENV PYTHONPATH=/app
ENV FLASK_MAX_CONTENT_LENGTH=209715200
ENV GUNICORN_TIMEOUT=600

# Expose port
EXPOSE 5000

# Run gunicorn with optimized settings for large uploads
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "600", "--max-requests", "1000", "--limit-request-line", "8190", "--limit-request-field_size", "8190", "main:app"]