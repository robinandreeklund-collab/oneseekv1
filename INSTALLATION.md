# SurfSense - Comprehensive Installation Guide

This guide provides complete installation instructions for SurfSense, including database setup, configuration, and deployment options.

## Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Quick Start (Docker)](#quick-start-docker)
- [Manual Installation](#manual-installation)
  - [PostgreSQL Setup](#postgresql-setup)
  - [Redis Setup](#redis-setup)
  - [Backend Setup](#backend-setup)
  - [Frontend Setup](#frontend-setup)
- [Configuration](#configuration)
- [Database Management](#database-management)
- [Production Deployment](#production-deployment)
- [Troubleshooting](#troubleshooting)

---

## Overview

SurfSense consists of several components:
- **Backend**: FastAPI application (Python 3.12+)
- **Database**: PostgreSQL 15+ with pgvector extension
- **Cache/Queue**: Redis 7+
- **Frontend**: Next.js application (Node.js 20+)
- **Worker**: Celery worker for background tasks

---

## Prerequisites

### System Requirements

- **CPU**: 2+ cores recommended
- **RAM**: 4GB minimum, 8GB+ recommended
- **Storage**: 20GB+ free space
- **OS**: Linux, macOS, or Windows (WSL2 recommended for Windows)

### Required Software

| Software | Version | Purpose |
|----------|---------|---------|
| Python | 3.12+ | Backend application |
| PostgreSQL | 15+ | Primary database |
| pgvector | 0.7.0+ | Vector embeddings |
| Redis | 7+ | Cache and task queue |
| Node.js | 20+ | Frontend application |
| Docker (optional) | 20+ | Containerized deployment |

---

## Quick Start (Docker)

The fastest way to get started is using Docker Compose, which handles all dependencies automatically.

### Option 1: All-in-One Docker Container

Perfect for evaluation and quick testing:

```bash
# Linux/macOS
docker run -d -p 3000:3000 -p 8000:8000 -p 5133:5133 \
  -v surfsense-data:/data \
  --name surfsense \
  --restart unless-stopped \
  ghcr.io/modsetter/surfsense:latest

# Windows (PowerShell)
docker run -d -p 3000:3000 -p 8000:8000 -p 5133:5133 `
  -v surfsense-data:/data `
  --name surfsense `
  --restart unless-stopped `
  ghcr.io/modsetter/surfsense:latest
```

Access:
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs

### Option 2: Docker Compose (Recommended for Production)

Full stack with separate services:

```bash
# Clone the repository
git clone https://github.com/MODSetter/SurfSense.git
cd SurfSense

# Copy environment file
cp .env.example .env

# Edit .env with your settings
nano .env

# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

**Services Started**:
- PostgreSQL with pgvector (port 5432)
- pgAdmin (port 5050)
- Redis (port 6379)
- Backend API (port 8000)
- Celery worker
- Celery beat (scheduler)
- Flower (task monitor, port 5555)
- ElectricSQL (port 5133)
- Frontend (port 3000)

---

## Manual Installation

For development or custom deployments, follow these steps for manual installation.

### PostgreSQL Setup

#### Linux (Ubuntu/Debian)

```bash
# Add PostgreSQL repository
sudo sh -c 'echo "deb http://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" > /etc/apt/sources.list.d/pgdg.list'
wget -qO- https://www.postgresql.org/media/keys/ACCC4CF8.asc | sudo tee /etc/apt/trusted.gpg.d/pgdg.asc &>/dev/null

# Install PostgreSQL 15
sudo apt update
sudo apt install -y postgresql-15 postgresql-contrib-15 postgresql-server-dev-15

# Start PostgreSQL
sudo systemctl start postgresql
sudo systemctl enable postgresql

# Check status
sudo systemctl status postgresql
```

#### macOS

```bash
# Using Homebrew
brew install postgresql@15
brew services start postgresql@15

# Or using Postgres.app
# Download from: https://postgresapp.com/
```

#### Windows

```bash
# Download installer from:
# https://www.postgresql.org/download/windows/
# Or use chocolatey:
choco install postgresql15

# Start service
net start postgresql-x64-15
```

#### Install pgvector Extension

pgvector is required for vector similarity search:

```bash
# Linux (Ubuntu/Debian)
sudo apt install -y postgresql-15-pgvector

# macOS
brew install pgvector

# Build from source (all platforms)
git clone https://github.com/pgvector/pgvector.git
cd pgvector
make
sudo make install
```

#### Create Database and User

```bash
# Switch to postgres user (Linux)
sudo -u postgres psql

# Or directly on macOS/Windows
psql postgres
```

In PostgreSQL prompt:

```sql
-- Create database
CREATE DATABASE surfsense;

-- Create user
CREATE USER surfsense_user WITH PASSWORD 'your_secure_password';

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE surfsense TO surfsense_user;

-- Connect to database
\c surfsense

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Grant schema privileges
GRANT ALL ON SCHEMA public TO surfsense_user;

-- Create electric user (for ElectricSQL)
CREATE USER electric WITH PASSWORD 'electric_password';
GRANT ALL PRIVILEGES ON DATABASE surfsense TO electric;

-- Exit
\q
```

#### Configure PostgreSQL

Edit `postgresql.conf` (location varies by OS):

```bash
# Find config location
sudo -u postgres psql -c "SHOW config_file;"

# Edit config (Linux example)
sudo nano /etc/postgresql/15/main/postgresql.conf
```

Recommended settings for SurfSense:

```conf
# Connection Settings
max_connections = 100
shared_buffers = 256MB
effective_cache_size = 1GB

# Performance Settings
work_mem = 16MB
maintenance_work_mem = 256MB
random_page_cost = 1.1

# WAL Settings (for ElectricSQL)
wal_level = logical
max_wal_senders = 10
max_replication_slots = 10

# Logging (optional, for debugging)
log_destination = 'stderr'
logging_collector = on
log_directory = 'log'
log_filename = 'postgresql-%Y-%m-%d_%H%M%S.log'
log_statement = 'all'
log_min_duration_statement = 1000
```

Restart PostgreSQL:

```bash
# Linux
sudo systemctl restart postgresql

# macOS
brew services restart postgresql@15

# Windows
net stop postgresql-x64-15
net start postgresql-x64-15
```

#### Update pg_hba.conf (Access Control)

Edit `pg_hba.conf`:

```bash
# Linux
sudo nano /etc/postgresql/15/main/pg_hba.conf
```

Add these lines for local development:

```conf
# TYPE  DATABASE        USER            ADDRESS                 METHOD
local   all             all                                     trust
host    all             all             127.0.0.1/32            md5
host    all             all             ::1/128                 md5
```

For Docker networks, add:

```conf
host    all             all             172.16.0.0/12           md5
```

Restart PostgreSQL after changes.

---

### Redis Setup

#### Linux (Ubuntu/Debian)

```bash
# Install Redis
sudo apt install -y redis-server

# Start Redis
sudo systemctl start redis-server
sudo systemctl enable redis-server

# Test connection
redis-cli ping
# Should return: PONG
```

#### macOS

```bash
# Using Homebrew
brew install redis
brew services start redis

# Test
redis-cli ping
```

#### Windows

```bash
# Using WSL2 (recommended)
sudo apt install redis-server
sudo service redis-server start

# Or download Redis for Windows:
# https://github.com/microsoftarchive/redis/releases
```

#### Configure Redis

Edit `/etc/redis/redis.conf` (Linux) or `/usr/local/etc/redis.conf` (macOS):

```conf
# Bind to localhost for security
bind 127.0.0.1

# Enable AOF persistence
appendonly yes
appendfilename "appendonly.aof"

# Memory settings
maxmemory 256mb
maxmemory-policy allkeys-lru

# Performance
tcp-backlog 511
timeout 0
tcp-keepalive 300
```

Restart Redis:

```bash
# Linux
sudo systemctl restart redis-server

# macOS
brew services restart redis
```

---

### Backend Setup

#### Install Python 3.12+

```bash
# Linux (Ubuntu 22.04+)
sudo apt install -y python3.12 python3.12-venv python3.12-dev

# macOS
brew install python@3.12

# Windows
# Download from: https://www.python.org/downloads/
```

#### Install uv (Fast Python Package Manager)

```bash
# Linux/macOS
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
irm https://astral.sh/uv/install.ps1 | iex

# Or use pip
pip install uv
```

#### Clone Repository and Setup

```bash
# Clone repository
git clone https://github.com/MODSetter/SurfSense.git
cd SurfSense

# Navigate to backend
cd surfsense_backend

# Create virtual environment
python3.12 -m venv venv

# Activate virtual environment
# Linux/macOS:
source venv/bin/activate
# Windows:
.\venv\Scripts\activate

# Install dependencies using uv (recommended)
uv pip install -e .

# Or using pip
pip install -e .

# Install Playwright browsers (for web scraping)
playwright install chromium
playwright install-deps
```

#### Create Environment File

```bash
# Copy example
cp .env.example .env

# Edit configuration
nano .env
```

**Minimum required settings**:

```bash
# Database
DATABASE_URL=postgresql+asyncpg://surfsense_user:your_secure_password@localhost:5432/surfsense

# Redis/Celery
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
REDIS_APP_URL=redis://localhost:6379/0

# Security
SECRET_KEY=your-secret-key-min-32-characters-long-use-random-string

# Frontend URL
NEXT_FRONTEND_URL=http://localhost:3000

# Authentication
AUTH_TYPE=LOCAL  # or GOOGLE for OAuth
REGISTRATION_ENABLED=TRUE

# Embedding Model (local, no API key needed)
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2

# File Processing
ETL_SERVICE=DOCLING  # or UNSTRUCTURED, LLAMACLOUD
```

#### Run Database Migrations

```bash
# Initialize Alembic (if needed)
alembic upgrade head

# The backend will also auto-create tables on first run
```

#### Start Backend Server

```bash
# Development mode with auto-reload
python main.py --reload

# Production mode
python main.py

# Or using uvicorn directly
uvicorn app.app:app --host 0.0.0.0 --port 8000 --reload
```

The backend should now be running at http://localhost:8000

**Test the backend**:

```bash
curl http://localhost:8000/docs
# Should return the API documentation page
```

#### Start Celery Worker

Open a new terminal:

```bash
cd surfsense_backend
source venv/bin/activate  # Activate virtual environment

# Start worker
celery -A celery_worker.celery_app worker --loglevel=info

# Start beat (scheduler) in another terminal
celery -A celery_worker.celery_app beat --loglevel=info

# Optional: Start Flower (task monitor)
celery -A celery_worker.celery_app flower --port=5555
# Access at http://localhost:5555
```

---

### Frontend Setup

#### Install Node.js

```bash
# Linux (using NodeSource)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs

# macOS
brew install node@20

# Windows
# Download from: https://nodejs.org/
# Or use Chocolatey:
choco install nodejs-lts
```

Verify installation:

```bash
node --version  # Should show v20.x.x
npm --version   # Should show 10.x.x
```

#### Install and Configure Frontend

```bash
# Navigate to frontend directory
cd surfsense_web

# Install dependencies
npm install

# Copy environment file
cp .env.example .env.local

# Edit configuration
nano .env.local
```

**Environment variables**:

```bash
# Backend API URL
NEXT_PUBLIC_FASTAPI_BACKEND_URL=http://localhost:8000

# Authentication type (must match backend)
NEXT_PUBLIC_FASTAPI_BACKEND_AUTH_TYPE=LOCAL
# Or: NEXT_PUBLIC_FASTAPI_BACKEND_AUTH_TYPE=GOOGLE

# ETL Service (must match backend)
NEXT_PUBLIC_ETL_SERVICE=DOCLING
# Or: UNSTRUCTURED, LLAMACLOUD

# ElectricSQL
NEXT_PUBLIC_ELECTRIC_URL=http://localhost:5133
NEXT_PUBLIC_ELECTRIC_AUTH_MODE=insecure

# Deployment mode
NEXT_PUBLIC_DEPLOYMENT_MODE=self-hosted
```

**Important**: 
- All `NEXT_PUBLIC_*` variables must be set BEFORE building/starting the frontend
- If you change these variables, restart the dev server or rebuild
- The `AUTH_TYPE` must match between frontend and backend

#### Start Development Server

```bash
# Development mode (with hot reload)
npm run dev

# Build for production
npm run build

# Start production server
npm start
```

The frontend should now be running at http://localhost:3000

---

## Configuration

### Environment Variables Reference

#### Database Configuration

```bash
# PostgreSQL connection
DATABASE_URL=postgresql+asyncpg://username:password@host:port/database

# Required: Set to TRUE for production, FALSE for testing only
DATABASE_REQUIRED=TRUE
```

#### Authentication Configuration

```bash
# Authentication type: LOCAL or GOOGLE
AUTH_TYPE=LOCAL

# Enable/disable user registration
REGISTRATION_ENABLED=TRUE

# Required: Set to TRUE for production, FALSE for testing only
AUTH_REQUIRED=TRUE

# For Google OAuth (if AUTH_TYPE=GOOGLE)
GOOGLE_OAUTH_CLIENT_ID=your_google_client_id
GOOGLE_OAUTH_CLIENT_SECRET=your_google_client_secret
```

**Setting up Google OAuth**:

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing
3. Enable Google+ API
4. Create OAuth 2.0 credentials
5. Add authorized redirect URIs:
   - `http://localhost:8000/auth/google/callback` (development)
   - `https://yourdomain.com/auth/google/callback` (production)
6. Copy Client ID and Client Secret to `.env`

#### LLM Configuration

```bash
# Embedding model
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
# Or with API key:
# EMBEDDING_MODEL=openai://text-embedding-ada-002
# OPENAI_API_KEY=sk-...

# LLM configurations are managed through:
# 1. Web UI (per-user settings)
# 2. Global config file: app/config/global_llm_config.yaml
```

**Create global LLM config** (optional):

```bash
cd surfsense_backend
mkdir -p app/config
nano app/config/global_llm_config.yaml
```

Example configuration:

```yaml
global_llm_configs:
  # OpenAI
  - id: -1
    name: "GPT-4"
    provider: "OPENAI"
    model_name: "gpt-4"
    api_key: "sk-..."
  
  # Local Ollama
  - id: -2
    name: "Llama 2"
    provider: "OLLAMA"
    model_name: "llama2"
    api_base: "http://localhost:11434"

router_settings:
  routing_strategy: "usage-based-routing"
  num_retries: 3
```

#### File Processing Configuration

```bash
# Choose ETL service: DOCLING (free), UNSTRUCTURED, or LLAMACLOUD
ETL_SERVICE=DOCLING

# For Unstructured.io
# UNSTRUCTURED_API_KEY=your_key

# For LlamaCloud
# LLAMA_CLOUD_API_KEY=your_key
```

#### Connector Configuration

SurfSense supports many external connectors. Configure as needed:

```bash
# Slack
SLACK_CLIENT_ID=your_slack_client_id
SLACK_CLIENT_SECRET=your_slack_client_secret
SLACK_REDIRECT_URI=http://localhost:8000/api/v1/auth/slack/connector/callback

# Google Calendar
GOOGLE_CALENDAR_REDIRECT_URI=http://localhost:8000/api/v1/auth/google/calendar/connector/callback

# GitHub (via Composio)
COMPOSIO_API_KEY=your_composio_key
COMPOSIO_ENABLED=TRUE

# See .env.example for full list of connectors
```

#### Text-to-Speech Configuration

```bash
# TTS Service: local/kokoro or LiteLLM provider
TTS_SERVICE=local/kokoro

# Or use cloud TTS
# TTS_SERVICE=openai/tts-1
# TTS_SERVICE_API_KEY=sk-...
```

#### Speech-to-Text Configuration

```bash
# STT Service: local/base (Faster-Whisper) or cloud
STT_SERVICE=local/base

# Available local models: tiny, base, small, medium, large-v3
# STT_SERVICE=local/large-v3

# Or use cloud STT
# STT_SERVICE=openai/whisper-1
# STT_SERVICE_API_KEY=sk-...
```

#### Reranker Configuration

```bash
# Enable rerankers for better search results
RERANKERS_ENABLED=TRUE
RERANKERS_MODEL_NAME=ms-marco-MiniLM-L-12-v2
RERANKERS_MODEL_TYPE=flashrank
```

---

## Database Management

### Backup Database

```bash
# Full backup
pg_dump -U surfsense_user -h localhost surfsense > surfsense_backup.sql

# Compressed backup
pg_dump -U surfsense_user -h localhost surfsense | gzip > surfsense_backup.sql.gz

# Backup with Docker Compose
docker-compose exec db pg_dump -U postgres surfsense > surfsense_backup.sql
```

### Restore Database

```bash
# Restore from backup
psql -U surfsense_user -h localhost surfsense < surfsense_backup.sql

# Restore compressed backup
gunzip -c surfsense_backup.sql.gz | psql -U surfsense_user -h localhost surfsense

# Restore with Docker Compose
docker-compose exec -T db psql -U postgres surfsense < surfsense_backup.sql
```

### Reset Database

⚠️ **Warning**: This will delete all data!

```bash
# Stop backend and workers
# Then drop and recreate database

sudo -u postgres psql
DROP DATABASE surfsense;
CREATE DATABASE surfsense;
\c surfsense
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
\q

# Run migrations
cd surfsense_backend
source venv/bin/activate
alembic upgrade head
```

### Database Migrations

SurfSense uses Alembic for database migrations:

```bash
cd surfsense_backend
source venv/bin/activate

# View current version
alembic current

# View migration history
alembic history

# Upgrade to latest
alembic upgrade head

# Downgrade one version
alembic downgrade -1

# Create new migration (after model changes)
alembic revision --autogenerate -m "Description of changes"
```

### Monitor Database Performance

```bash
# Using psql
sudo -u postgres psql surfsense

-- Check database size
SELECT pg_size_pretty(pg_database_size('surfsense'));

-- Check table sizes
SELECT schemaname, tablename, 
       pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

-- Check active connections
SELECT count(*) FROM pg_stat_activity;

-- Check long-running queries
SELECT pid, now() - pg_stat_activity.query_start AS duration, query
FROM pg_stat_activity
WHERE state = 'active' AND now() - pg_stat_activity.query_start > interval '5 seconds'
ORDER BY duration DESC;
```

### Using pgAdmin

Access pgAdmin (if using Docker Compose):
1. Open http://localhost:5050
2. Login: admin@surfsense.com / surfsense
3. Add server:
   - Name: SurfSense
   - Host: db (or localhost)
   - Port: 5432
   - Database: surfsense
   - Username: surfsense_user
   - Password: (your password)

---

## Production Deployment

### Security Checklist

- [ ] Change all default passwords
- [ ] Use strong SECRET_KEY (32+ random characters)
- [ ] Enable HTTPS with valid SSL certificate
- [ ] Set `DATABASE_REQUIRED=TRUE` and `AUTH_REQUIRED=TRUE`
- [ ] Configure firewall (only expose necessary ports)
- [ ] Use environment variables (not .env files) in production
- [ ] Enable PostgreSQL authentication (md5 or scram-sha-256)
- [ ] Restrict Redis to localhost or use password
- [ ] Regular backups (automated)
- [ ] Enable logging and monitoring
- [ ] Use rate limiting
- [ ] Configure CORS properly

### Recommended Production Setup

#### 1. Reverse Proxy (Nginx)

```nginx
# /etc/nginx/sites-available/surfsense
server {
    listen 80;
    server_name yourdomain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name yourdomain.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    # Frontend
    location / {
        proxy_pass http://localhost:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }

    # Backend API
    location /api {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket support
        proxy_read_timeout 86400;
    }
}
```

Enable site:

```bash
sudo ln -s /etc/nginx/sites-available/surfsense /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

#### 2. Systemd Services

**Backend service** (`/etc/systemd/system/surfsense-backend.service`):

```ini
[Unit]
Description=SurfSense Backend
After=network.target postgresql.service redis.service

[Service]
Type=simple
User=surfsense
WorkingDirectory=/opt/surfsense/surfsense_backend
Environment="PATH=/opt/surfsense/surfsense_backend/venv/bin"
ExecStart=/opt/surfsense/surfsense_backend/venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Celery worker** (`/etc/systemd/system/surfsense-worker.service`):

```ini
[Unit]
Description=SurfSense Celery Worker
After=network.target redis.service

[Service]
Type=simple
User=surfsense
WorkingDirectory=/opt/surfsense/surfsense_backend
Environment="PATH=/opt/surfsense/surfsense_backend/venv/bin"
ExecStart=/opt/surfsense/surfsense_backend/venv/bin/celery -A celery_worker.celery_app worker --loglevel=info
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Celery beat** (`/etc/systemd/system/surfsense-beat.service`):

```ini
[Unit]
Description=SurfSense Celery Beat
After=network.target redis.service

[Service]
Type=simple
User=surfsense
WorkingDirectory=/opt/surfsense/surfsense_backend
Environment="PATH=/opt/surfsense/surfsense_backend/venv/bin"
ExecStart=/opt/surfsense/surfsense_backend/venv/bin/celery -A celery_worker.celery_app beat --loglevel=info
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Frontend service** (`/etc/systemd/system/surfsense-frontend.service`):

```ini
[Unit]
Description=SurfSense Frontend
After=network.target

[Service]
Type=simple
User=surfsense
WorkingDirectory=/opt/surfsense/surfsense_web
Environment="PATH=/usr/bin:/usr/local/bin"
Environment="NODE_ENV=production"
ExecStart=/usr/bin/npm start
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start services:

```bash
sudo systemctl daemon-reload
sudo systemctl enable surfsense-backend surfsense-worker surfsense-beat surfsense-frontend
sudo systemctl start surfsense-backend surfsense-worker surfsense-beat surfsense-frontend

# Check status
sudo systemctl status surfsense-backend
```

#### 3. Environment Variables in Production

Don't use `.env` files in production. Set environment variables directly:

```bash
# Add to /etc/environment or use systemd Environment=
# Or use secrets management like Vault, AWS Secrets Manager
```

#### 4. Logging Configuration

```bash
# Create log directories
sudo mkdir -p /var/log/surfsense
sudo chown surfsense:surfsense /var/log/surfsense

# Configure log rotation
sudo nano /etc/logrotate.d/surfsense
```

Add:

```
/var/log/surfsense/*.log {
    daily
    missingok
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 surfsense surfsense
    sharedscripts
}
```

#### 5. Monitoring

Consider using:
- **Prometheus + Grafana**: Metrics and visualization
- **Sentry**: Error tracking
- **Flower**: Celery task monitoring
- **pgAdmin**: Database monitoring
- **Redis Commander**: Redis monitoring

---

## Troubleshooting

### Common Issues

#### 1. Database Connection Errors

**Error**: `could not connect to server: Connection refused`

**Solutions**:
```bash
# Check if PostgreSQL is running
sudo systemctl status postgresql

# Check if database exists
sudo -u postgres psql -l

# Check connection settings
psql "postgresql://username:password@localhost:5432/surfsense"

# Check pg_hba.conf allows connections
sudo nano /etc/postgresql/15/main/pg_hba.conf
```

#### 2. pgvector Extension Missing

**Error**: `extension "vector" is not available`

**Solutions**:
```bash
# Install pgvector
sudo apt install postgresql-15-pgvector

# Or build from source
git clone https://github.com/pgvector/pgvector.git
cd pgvector
make
sudo make install

# Enable in database
sudo -u postgres psql surfsense
CREATE EXTENSION vector;
```

#### 3. Redis Connection Issues

**Error**: `Error 111 connecting to localhost:6379. Connection refused.`

**Solutions**:
```bash
# Check if Redis is running
sudo systemctl status redis-server

# Start Redis
sudo systemctl start redis-server

# Test connection
redis-cli ping

# Check Redis config
sudo nano /etc/redis/redis.conf
# Ensure: bind 127.0.0.1
```

#### 4. Port Already in Use

**Error**: `Address already in use`

**Solutions**:
```bash
# Find process using port 8000
sudo lsof -i :8000
# Or
sudo netstat -tulpn | grep :8000

# Kill process
sudo kill -9 <PID>

# Or use different port
python main.py --port 8001
```

#### 5. Permission Denied Errors

**Solutions**:
```bash
# Fix ownership
sudo chown -R $USER:$USER .

# Fix permissions
chmod +x quick-start-testing.sh

# PostgreSQL permissions
sudo -u postgres psql
GRANT ALL PRIVILEGES ON DATABASE surfsense TO surfsense_user;
GRANT ALL ON SCHEMA public TO surfsense_user;
```

#### 6. Module Not Found Errors

**Error**: `ModuleNotFoundError: No module named 'fastapi'`

**Solutions**:
```bash
# Ensure virtual environment is activated
source venv/bin/activate

# Reinstall dependencies
pip install -e .

# Or use uv
uv pip install -e .
```

#### 7. Migration Errors

**Error**: `Target database is not up to date`

**Solutions**:
```bash
cd surfsense_backend
source venv/bin/activate

# Check current version
alembic current

# Upgrade to latest
alembic upgrade head

# If migration fails, check PostgreSQL logs
sudo tail -f /var/log/postgresql/postgresql-15-main.log
```

#### 8. Celery Tasks Not Running

**Solutions**:
```bash
# Check if worker is running
ps aux | grep celery

# Check Redis connection
redis-cli ping

# Start worker with debug logging
celery -A celery_worker.celery_app worker --loglevel=debug

# Check Flower for task status
# http://localhost:5555
```

#### 9. Frontend Build Errors

**Solutions**:
```bash
cd surfsense_web

# Clear cache
rm -rf .next node_modules package-lock.json

# Reinstall dependencies
npm install

# Try building again
npm run build
```

#### 10. Out of Memory Errors

**Solutions**:
```bash
# Check available memory
free -h

# Reduce PostgreSQL shared_buffers
sudo nano /etc/postgresql/15/main/postgresql.conf
# Set: shared_buffers = 128MB

# Reduce worker concurrency
celery -A celery_worker.celery_app worker --concurrency=2

# Add swap space (Linux)
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
```

### Getting Help

If you encounter issues not covered here:

1. **Check logs**:
   - Backend: `tail -f surfsense_backend/logs/*.log`
   - PostgreSQL: `/var/log/postgresql/postgresql-*.log`
   - Celery: Check worker terminal output

2. **Search GitHub Issues**: [SurfSense Issues](https://github.com/MODSetter/SurfSense/issues)

3. **Ask in Discord**: [SurfSense Discord](https://discord.gg/ejRNvftDp9)

4. **Review documentation**:
   - [TESTING_WITHOUT_DATABASE.md](TESTING_WITHOUT_DATABASE.md) - Testing mode
   - [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md) - Technical details
   - [README.md](README.md) - Quick start

---

## Additional Resources

### Documentation
- [Official Documentation](https://www.surfsense.com/docs/)
- [Docker Installation](https://www.surfsense.com/docs/docker-installation)
- [Manual Installation](https://www.surfsense.com/docs/manual-installation)

### External Resources
- [PostgreSQL Documentation](https://www.postgresql.org/docs/)
- [pgvector Documentation](https://github.com/pgvector/pgvector)
- [Redis Documentation](https://redis.io/docs/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Next.js Documentation](https://nextjs.org/docs)
- [Celery Documentation](https://docs.celeryq.dev/)

### Community
- [GitHub Repository](https://github.com/MODSetter/SurfSense)
- [Discord Server](https://discord.gg/ejRNvftDp9)
- [Reddit Community](https://www.reddit.com/r/SurfSense/)

---

## License

SurfSense is open-source software licensed under the [Apache License 2.0](LICENSE).

---

**Last Updated**: February 2026

For the latest updates, visit: https://github.com/MODSetter/SurfSense
