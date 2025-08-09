# Gunicorn configuration for production

import os

# Server socket
bind = f"0.0.0.0:{os.environ.get('PORT', 8000)}"

# Worker processes
workers = int(os.environ.get('GUNICORN_WORKERS', 2))
worker_class = "sync"
worker_connections = 1000
timeout = 30
keepalive = 2

# Restart workers after this many requests, to help prevent memory leaks
max_requests = 1000
max_requests_jitter = 50

# Log to stdout
accesslog = '-'
errorlog = '-'
loglevel = 'info'

# Process naming
proc_name = 'energo_fakturace'

# Server mechanics
daemon = False
pidfile = None
user = None
group = None
tmp_upload_dir = None

# SSL (if needed)
# keyfile = None
# certfile = None