import os
import multiprocessing

# Server socket
bind = "0.0.0.0:5000"
backlog = 2048

# Worker processes
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "sync"
worker_connections = 1000
timeout = 300  # 5 minutes for large file processing
keepalive = 2

# Restart workers after this many requests, to help prevent memory leaks
max_requests = 1000
max_requests_jitter = 50

# Logging
loglevel = "info"
accesslog = "-"
errorlog = "-"

# Process naming
proc_name = "audio_splitter_app"

# Server mechanics
preload_app = True
sendfile = False
reuse_port = True

# Application settings
raw_env = [
    'DJANGO_SETTINGS_MODULE=myproject.settings',
]

# Large file upload support
limit_request_line = 8190
limit_request_fields = 100
limit_request_field_size = 8190