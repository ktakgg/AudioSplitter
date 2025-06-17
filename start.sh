#!/bin/bash

# Startup script for both development and deployment environments

# Set environment variables for deployment
export FLASK_MAX_CONTENT_LENGTH=${FLASK_MAX_CONTENT_LENGTH:-209715200}
export GUNICORN_TIMEOUT=${GUNICORN_TIMEOUT:-600}
export PYTHONPATH=${PYTHONPATH:-"."}

# Check if running in deployment environment
if [ "$REPLIT_DEPLOYMENT" = "1" ]; then
    echo "Starting in deployment mode..."
    # Production settings with optimized configuration for Cloud Run
    exec gunicorn \
        --bind 0.0.0.0:5000 \
        --workers 2 \
        --worker-class sync \
        --timeout 600 \
        --keep-alive 2 \
        --max-requests 1000 \
        --max-requests-jitter 50 \
        --preload \
        --limit-request-line 8190 \
        --limit-request-field_size 8190 \
        --access-logfile - \
        --error-logfile - \
        --log-level info \
        main:app
else
    echo "Starting in development mode..."
    # Development settings
    exec gunicorn \
        --bind 0.0.0.0:5000 \
        --reuse-port \
        --reload \
        --timeout 600 \
        --limit-request-line 8190 \
        --limit-request-field_size 8190 \
        main:app
fi