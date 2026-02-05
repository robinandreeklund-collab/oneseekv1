# Getting Started with SurfSense

Welcome to SurfSense! This guide will help you create an account, log in, and start using the platform.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Accessing the Platform](#accessing-the-platform)
- [Creating an Account](#creating-an-account)
- [Logging In](#logging-in)
- [First Time Setup](#first-time-setup)
- [Using SurfSense](#using-surfsense)
- [Troubleshooting](#troubleshooting)

---

## Prerequisites

Before getting started, make sure you have:

✅ **SurfSense is running** - Follow the [Installation Guide](INSTALLATION.md) if not already installed
✅ **Know your authentication method** - Either LOCAL (email/password) or GOOGLE (OAuth)

### Check if SurfSense is Running

```bash
# Check if services are running
curl http://localhost:8000/docs
# Should return the API documentation page

curl http://localhost:3000
# Should return the frontend
```

If you get connection errors, refer to the [Installation Guide](INSTALLATION.md) or [Troubleshooting](#troubleshooting) section.

---

## Accessing the Platform

Once SurfSense is running, access it through your web browser:

### Default URLs

| Service | URL | Description |
|---------|-----|-------------|
| **Frontend** | http://localhost:3000 | Main application interface |
| **Backend API** | http://localhost:8000 | API server |
| **API Docs** | http://localhost:8000/docs | Interactive API documentation |
| **Flower** | http://localhost:5555 | Task queue monitor (if running) |
| **pgAdmin** | http://localhost:5050 | Database admin (if using Docker Compose) |

**Primary URL**: Open your browser and go to **http://localhost:3000**

---

## Creating an Account

SurfSense supports two authentication methods:

### Method 1: Local Authentication (Email/Password)

This is the default method if `AUTH_TYPE=LOCAL` in your `.env` file.

#### Steps:

1. **Open SurfSense** in your browser: http://localhost:3000

2. **Click "Sign Up" or "Register"** (usually in the top-right corner or on the login page)

3. **Fill in the registration form**:
   - **Email**: Your email address (e.g., user@example.com)
   - **Password**: Choose a strong password (minimum 8 characters recommended)
   - **Confirm Password**: Re-enter your password

4. **Click "Create Account" or "Register"**

5. **Check your email** (if email verification is enabled):
   - Look for a verification email from SurfSense
   - Click the verification link
   - If email is not configured, your account may be active immediately

6. **Login** with your new credentials

#### Example Registration Form

```
┌─────────────────────────────────────┐
│     Create Your SurfSense Account   │
├─────────────────────────────────────┤
│                                     │
│  Email:    [                      ] │
│  Password: [                      ] │
│  Confirm:  [                      ] │
│                                     │
│  [ Create Account ]                 │
│                                     │
│  Already have an account? [Login]   │
└─────────────────────────────────────┘
```

### Method 2: Google OAuth

If `AUTH_TYPE=GOOGLE` is configured in your `.env` file.

#### Prerequisites:
- Google OAuth must be configured with valid `GOOGLE_OAUTH_CLIENT_ID` and `GOOGLE_OAUTH_CLIENT_SECRET`
- See [Installation Guide - Authentication Configuration](INSTALLATION.md#authentication-configuration) for setup

#### Steps:

1. **Open SurfSense** in your browser: http://localhost:3000

2. **Click "Sign in with Google"** button

3. **Select your Google account** in the popup window

4. **Grant permissions** to SurfSense when prompted

5. **You're logged in!** Your account is automatically created on first login

#### What Happens:
- Your Google account (email, name, profile picture) is used
- No password needed - Google handles authentication
- Automatic account creation on first sign-in

---

## Logging In

### Local Authentication Login

1. Go to http://localhost:3000

2. If not already logged in, you'll see the login page

3. Enter your credentials:
   - **Email**: The email you registered with
   - **Password**: Your password

4. Click **"Login"** or **"Sign In"**

5. You're in! The dashboard will load

### Google OAuth Login

1. Go to http://localhost:3000

2. Click **"Sign in with Google"**

3. Select your Google account (or enter credentials)

4. You're automatically logged in

### Staying Logged In

- SurfSense uses JWT tokens that expire after 24 hours
- Your session will persist across browser restarts
- You'll need to log in again after token expiration

---

## First Time Setup

After logging in for the first time, you'll need to set up your workspace:

### 1. Welcome Screen

You may see a welcome or onboarding screen. Follow the prompts to:
- Set up your profile
- Choose your preferences
- Take a quick tour (optional)

### 2. Create Your First Search Space

**Search Spaces** are workspaces where you organize documents and chats.

#### Steps:

1. **Look for "Create Search Space"** button or menu option

2. **Enter details**:
   - **Name**: Give it a meaningful name (e.g., "My Research", "Work Documents")
   - **Description**: Optional description of what you'll use it for

3. **Click "Create"**

4. Your search space is now ready!

### 3. Configure LLM Settings (Optional)

To use AI chat features, you need to configure a Large Language Model.

#### Option A: Use Global LLM Config

If your admin has set up global LLM configurations in `global_llm_config.yaml`, you can select from pre-configured models.

#### Option B: Add Your Own LLM

1. Go to **Settings** or **Search Space Settings**

2. Navigate to **LLM Configurations**

3. Click **"Add LLM Configuration"**

4. Fill in the details:

**For OpenAI:**
```
Provider: OpenAI
Model Name: gpt-4 (or gpt-3.5-turbo)
API Key: sk-your-api-key-here
```

**For Local LLM (Ollama):**
```
Provider: Ollama
Model Name: llama2
API Base: http://localhost:11434
API Key: (leave empty)
```

**For vLLM:**
```
Provider: Ollama (works with OpenAI-compatible endpoints)
Model Name: your-model-name
API Base: http://localhost:8001/v1
API Key: EMPTY
```

5. Click **"Test Configuration"** to verify it works

6. Click **"Save"**

### 4. Set Default LLM

1. Go to **Search Space Settings**

2. Under **LLM Settings**, select:
   - **Agent LLM**: For chat and agent operations
   - **Document Summary LLM**: For document summarization

3. Click **"Save"**

---

## Using SurfSense

Now you're ready to use the platform!

### Upload Documents

1. **Navigate to your Search Space**

2. **Click "Upload" or "Add Document"**

3. **Choose your upload method**:
   - **File Upload**: Upload PDFs, Word docs, images, etc. (50+ formats supported)
   - **Web URL**: Enter a URL to crawl and index
   - **YouTube Video**: Paste a YouTube URL to index the transcript

4. **Wait for processing**: Documents are processed in the background

5. **View your documents** in the documents list

### Start Chatting

1. **Click "New Chat" or "Start Conversation"**

2. **Type your question** in the chat box

3. **Press Enter or click Send**

4. SurfSense will:
   - Search your documents
   - Use the configured LLM
   - Provide answers with citations

### Example Chat

```
You: What are the key findings in my research documents?

SurfSense: Based on your documents, here are the key findings:
1. [Finding 1] - Source: Document A, Page 5
2. [Finding 2] - Source: Document B, Page 12
3. [Finding 3] - Source: Document C, Page 8
...
```

### Advanced Features

#### Generate Podcasts

1. Have a conversation in chat
2. Click **"Generate Podcast"** button
3. Wait for generation (usually under 30 seconds)
4. Listen to your AI-generated podcast!

#### Connect External Sources

Add connectors to integrate external data:

1. Go to **Settings** → **Connectors**

2. Choose a connector (Slack, Google Drive, Notion, GitHub, etc.)

3. Follow the OAuth flow to connect

4. Your data will be indexed automatically

#### Team Collaboration

If you have team members:

1. Go to **Search Space Settings** → **Members**

2. Click **"Invite Member"**

3. Enter their email and choose a role:
   - **Owner**: Full control
   - **Admin**: Manage settings and members
   - **Editor**: Edit documents and chats
   - **Viewer**: Read-only access

4. They'll receive an invitation email

---

## Troubleshooting


### NPM Install Dependency Conflicts

**Problem**: `npm install` fails with dependency resolution errors like "ERESOLVE unable to resolve dependency tree"

**Common errors**:
```
# Assistant-ui packages conflict
Could not resolve dependency:
peer @assistant-ui/react@"^0.12.6" from @assistant-ui/react-ai-sdk@1.3.5

# Fumadocs/Zod conflict
Conflicting peer dependency: zod@4.3.6
peerOptional zod@"4.x.x" from fumadocs-core@16.5.0

# AI SDK / Zod version conflict
Could not resolve dependency:
peer zod@"^3.23.8" from ai@4.3.19
(Requires upgrading to ai@6.x which supports zod 4.x)

# React 19 / emblor conflict
Could not resolve dependency:
peer react@"^18.0.0" from emblor@1.4.8
(Fixed with .npmrc legacy-peer-deps=true)

# Other peer dependency conflicts
Could not resolve dependency: peer X from Y
```

**Solutions**:

1. **Clear npm cache and reinstall** (try this first):
   ```bash
   cd surfsense_web
   rm -rf node_modules package-lock.json
   npm cache clean --force
   npm install
   ```

2. **Use legacy peer deps** (for React 19 compatibility):
   
   If you get errors about packages requiring React 18 (like emblor@1.4.8):
   ```bash
   # The repository includes an .npmrc file with legacy-peer-deps=true
   # This allows React 19 to work with packages that haven't updated yet
   
   # If .npmrc is missing, create it:
   echo "legacy-peer-deps=true" > .npmrc
   
   # Then install:
   npm install
   ```
   
   This is safe because React 19 is backward compatible with React 18 components.

3. **Check Node.js version**:
   ```bash
   node --version
   # Should be v20.x.x or higher
   ```
   
   If using older Node.js, update it:
   ```bash
   # Using nvm
   nvm install 20
   nvm use 20
   ```

4. **WSL-specific: Clear Windows npm cache**:
   If you previously ran npm in Windows PowerShell:
   ```bash
   # In WSL
   rm -rf node_modules package-lock.json
   
   # Clear global cache
   npm cache clean --force
   
   # Install fresh
   npm install
   ```

5. **Verify package.json is up to date**:
   Make sure you have the latest version from the repository:
   ```bash
   git pull origin main
   ```

**If none of these work**, check the [GitHub Issues](https://github.com/MODSetter/SurfSense/issues) for known dependency conflicts.


### Cannot Access http://localhost:3000

**Problem**: Browser shows "Connection refused" or "This site can't be reached"

**Solutions**:

1. Check if frontend is running:
   ```bash
   # If using Docker
   docker ps | grep surfsense
   
   # If running manually
   ps aux | grep "npm\|node"
   ```

2. Start the frontend if not running:
   ```bash
   # Docker
   docker-compose up -d
   
   # Manual
   cd surfsense_web
   npm start
   ```

3. Check logs for errors:
   ```bash
   # Docker
   docker-compose logs frontend
   
   # Manual
   # Check terminal where you ran npm start
   ```

### Cannot Create Account

**Problem**: Registration form doesn't work or shows errors

**Solutions**:

1. **Check if registration is enabled**:
   ```bash
   # In surfsense_backend/.env
   grep REGISTRATION_ENABLED .env
   # Should show: REGISTRATION_ENABLED=TRUE
   ```

2. **Check backend is running**:
   ```bash
   curl http://localhost:8000/docs
   ```

3. **Check database connection**:
   ```bash
   # Docker
   docker-compose ps db
   
   # Manual
   sudo systemctl status postgresql
   ```

4. **Check backend logs**:
   ```bash
   # Docker
   docker-compose logs backend
   
   # Manual
   tail -f surfsense_backend/logs/*.log
   ```

### Login Fails

**Problem**: Correct credentials but login doesn't work

**Solutions**:

1. **Clear browser cache and cookies**:
   - Press Ctrl+Shift+Delete (or Cmd+Shift+Delete on Mac)
   - Clear cache and cookies
   - Try logging in again

2. **Check if email verification is required**:
   - Look for verification email in your inbox/spam
   - Click the verification link

3. **Reset password** (LOCAL auth):
   - Click "Forgot Password" on login page
   - Follow the reset process

4. **Check backend API**:
   ```bash
   curl -X POST http://localhost:8000/auth/jwt/login \
     -H "Content-Type: application/x-www-form-urlencoded" \
     -d "username=your@email.com&password=yourpassword"
   ```

### Turbopack/Next.js Error After Login

**Problem**: After successful login, you see "Runtime Error: An unexpected Turbopack error occurred" on the dashboard

**This is a common issue with Next.js 16+ and can have several causes:**

**Solutions**:

1. **Check frontend environment variables**:
   ```bash
   cd surfsense_web
   
   # Ensure .env.local exists with proper values
   cat .env.local
   
   # Should contain:
   # NEXT_PUBLIC_FASTAPI_BACKEND_URL=http://localhost:8000
   # NEXT_PUBLIC_FASTAPI_BACKEND_AUTH_TYPE=LOCAL  (or GOOGLE)
   # NEXT_PUBLIC_ETL_SERVICE=DOCLING
   # NEXT_PUBLIC_ELECTRIC_URL=http://localhost:5133
   # NEXT_PUBLIC_ELECTRIC_AUTH_MODE=insecure
   # NEXT_PUBLIC_DEPLOYMENT_MODE=self-hosted
   ```

2. **Restart frontend with clean cache**:
   ```bash
   cd surfsense_web
   
   # Stop the dev server (Ctrl+C)
   # Clear Next.js cache
   rm -rf .next
   
   # Reinstall dependencies (if needed)
   npm install
   
   # Start fresh
   npm run dev
   ```

3. **Check ElectricSQL is running**:
   ```bash
   # ElectricSQL must be running for the frontend to work
   curl http://localhost:5133
   
   # If not running, start it:
   # Docker:
   docker-compose up -d electric
   
   # Manual: check INSTALLATION.md for ElectricSQL setup
   ```

4. **Check backend API is accessible**:
   ```bash
   # Test backend connection
   curl http://localhost:8000/api/v1/search-spaces
   
   # Should return search spaces data or 401 (both are OK)
   ```

5. **Check browser console for detailed errors**:
   - Press F12 to open Developer Tools
   - Go to Console tab
   - Look for specific error messages
   - Common issues:
     - CORS errors (check NEXT_FRONTEND_URL in backend .env)
     - API connection failures (check backend is running)
     - Environment variable missing (check .env.local)

6. **Try production build**:
   ```bash
   cd surfsense_web
   npm run build
   npm start
   ```

7. **Check if you have a default search space**:
   ```bash
   # Query database to see if user has search spaces
   sudo -u postgres psql surfsense
   SELECT id, name, owner_id FROM search_spaces;
   \q
   ```
   
   If no search spaces exist, the dashboard should redirect to create one. If this doesn't happen, check frontend logs.

8. **Verify Node.js version**:
   ```bash
   node --version
   # Should be v20.x.x or higher
   
   # If lower, upgrade Node.js
   ```

9. **Check for port conflicts**:
   ```bash
   # Make sure ports aren't already in use
   lsof -i :3000  # Frontend
   lsof -i :8000  # Backend
   lsof -i :5133  # ElectricSQL
   ```

10. **Review terminal output**:
    - Look at the terminal where you ran `npm run dev`
    - Turbopack errors often show more details there
    - Look for compilation errors or module resolution issues


### WSL and Windows Mixed Environment Issues

**Problem**: Backend runs in WSL, frontend runs in Windows PowerShell - Turbopack errors or connection failures

**This is a common networking issue!** WSL and Windows have different network stacks. When backend runs in WSL and frontend in Windows:
- `localhost` in Windows ≠ `localhost` in WSL
- Frontend cannot reach backend at `localhost:8000`
- ElectricSQL in WSL is not accessible from Windows

**Solutions**:

#### Solution 1: Run Everything in WSL (Recommended)

Run the frontend in WSL alongside the backend:

```bash
# In WSL terminal
cd /path/to/surfsense/surfsense_web
npm run dev
```

Access from Windows browser: `http://localhost:3000` (WSL forwards ports automatically)

#### Solution 2: Use WSL IP Address in Frontend

If you must run frontend in Windows PowerShell:

1. **Find WSL IP address**:
   ```bash
   # In WSL terminal
   ip addr show eth0 | grep "inet " | awk '{print $2}' | cut -d/ -f1
   # Example output: 172.24.144.1
   ```

2. **Update frontend environment variables** (in Windows):
   ```bash
   # In PowerShell, edit surfsense_web\.env.local
   NEXT_PUBLIC_FASTAPI_BACKEND_URL=http://172.24.144.1:8000
   NEXT_PUBLIC_ELECTRIC_URL=http://172.24.144.1:5133
   ```

3. **Update backend CORS settings**:
   ```bash
   # In WSL, edit surfsense_backend/.env
   NEXT_FRONTEND_URL=http://localhost:3000
   # Or use Windows IP if needed
   ```

4. **Restart both services**:
   ```bash
   # In WSL - restart backend
   cd surfsense_backend
   python main.py
   
   # In PowerShell - restart frontend
   cd surfsense_web
   npm run dev
   ```

#### Solution 3: Port Forwarding (Alternative)

Configure WSL to forward ports to Windows:

```powershell
# In PowerShell (Administrator)
netsh interface portproxy add v4tov4 listenport=8000 listenaddress=0.0.0.0 connectport=8000 connectaddress=172.24.144.1
netsh interface portproxy add v4tov4 listenport=5133 listenaddress=0.0.0.0 connectport=5133 connectaddress=172.24.144.1

# View current port forwarding
netsh interface portproxy show all

# Remove forwarding (if needed)
netsh interface portproxy delete v4tov4 listenport=8000 listenaddress=0.0.0.0
```

**Note**: WSL IP address changes on restart, so Solution 1 is most reliable.

#### Solution 4: Use Docker (Best for Windows)

Run everything in Docker to avoid WSL/Windows networking issues:

```powershell
# In PowerShell
cd surfsense
docker-compose up -d
```

Access at `http://localhost:3000`

#### Verify the Setup

After applying a solution, verify connectivity:

```bash
# From Windows PowerShell
curl http://localhost:8000/docs
# Should return HTML (backend accessible)

curl http://localhost:5133
# Should return response (ElectricSQL accessible)

curl http://localhost:3000
# Should return HTML (frontend accessible)
```

#### Common WSL IP Addresses

WSL typically uses IPs in these ranges:
- `172.x.x.x` (most common)
- `192.168.x.x`
- Changes after Windows/WSL restart

**Best Practice**: Always run all services in the same environment (all WSL or all Docker) to avoid networking complexity.

### Google OAuth Not Working

**Problem**: "Sign in with Google" button doesn't work or shows errors

**Solutions**:

1. **Verify OAuth configuration**:
   ```bash
   # Check .env file
   grep GOOGLE_OAUTH surfsense_backend/.env
   ```

2. **Check redirect URIs** in Google Cloud Console:
   - Must include: `http://localhost:8000/auth/google/callback`
   - Or your production URL: `https://yourdomain.com/auth/google/callback`

3. **Enable Google+ API** in Google Cloud Console

4. **Check browser console** for JavaScript errors:
   - Press F12 to open developer tools
   - Check Console tab for errors

### No LLM Available

**Problem**: Can't chat because no LLM is configured

**Solutions**:

1. **Add an LLM configuration** (see [Configure LLM Settings](#3-configure-llm-settings-optional))

2. **Use global LLM config**:
   ```bash
   # Create config file
   mkdir -p surfsense_backend/app/config
   nano surfsense_backend/app/config/global_llm_config.yaml
   ```

   Add:
   ```yaml
   global_llm_configs:
     - id: -1
       name: "Local Ollama"
       provider: "OLLAMA"
       model_name: "llama2"
       api_base: "http://localhost:11434"
   ```

3. **Start local LLM** (Ollama example):
   ```bash
   ollama serve
   ollama pull llama2
   ```

### Documents Not Processing

**Problem**: Uploaded documents stuck in processing

**Solutions**:

1. **Check Celery worker is running**:
   ```bash
   # Docker
   docker-compose ps worker
   
   # Manual
   ps aux | grep celery
   ```

2. **Start Celery worker** if not running:
   ```bash
   cd surfsense_backend
   source venv/bin/activate
   celery -A celery_worker.celery_app worker --loglevel=info
   ```

3. **Check Flower** (task monitor):
   - Open http://localhost:5555
   - Look for failed tasks
   - Check error messages

4. **Check file format is supported**:
   - See [Supported File Extensions](README.md#-supported-file-extensions)
   - Try a different file format

### Slow Performance

**Problem**: Platform is slow or unresponsive

**Solutions**:

1. **Check system resources**:
   ```bash
   # Memory usage
   free -h
   
   # CPU usage
   top
   
   # Docker stats
   docker stats
   ```

2. **Reduce worker concurrency** if low on memory:
   ```bash
   celery -A celery_worker.celery_app worker --concurrency=2
   ```

3. **Reduce PostgreSQL memory** in `postgresql.conf`:
   ```conf
   shared_buffers = 128MB  # Instead of 256MB
   ```

4. **Close unused browser tabs** and refresh the page

---

## Next Steps

Now that you're set up, explore more features:

📚 **Learn More**:
- [Installation Guide](INSTALLATION.md) - Complete installation details
- [Testing Without Database](TESTING_WITHOUT_DATABASE.md) - Testing mode
- [Documentation Guide](DOCUMENTATION_GUIDE.md) - Navigate all docs

🔧 **Advanced Configuration**:
- Configure external connectors (Slack, GitHub, Notion)
- Set up team collaboration with RBAC
- Configure custom LLM providers
- Enable podcast generation
- Set up speech-to-text and text-to-speech

🎓 **Video Tutorials**:
- Check the [README](README.md) for video demonstrations
- Join [Discord](https://discord.gg/ejRNvftDp9) for community support
- Visit [SurfSense Cloud](https://www.surfsense.com/) for hosted version

---

## Getting Help

If you encounter issues not covered here:

### Check Documentation
- [Installation Guide](INSTALLATION.md) - Comprehensive setup and troubleshooting
- [README](README.md) - Overview and quick start
- [GitHub Issues](https://github.com/MODSetter/SurfSense/issues) - Known issues and solutions

### Community Support
- **Discord**: [Join SurfSense Discord](https://discord.gg/ejRNvftDp9)
- **Reddit**: [r/SurfSense](https://www.reddit.com/r/SurfSense/)
- **GitHub Discussions**: [Ask questions](https://github.com/MODSetter/SurfSense/discussions)

### Report Bugs
- [Create an issue](https://github.com/MODSetter/SurfSense/issues/new) on GitHub
- Include:
  - What you were trying to do
  - What happened instead
  - Error messages (check browser console and backend logs)
  - Your setup (Docker/manual, OS, versions)

---

## Quick Reference

### Common Commands

```bash
# Check if services are running
curl http://localhost:3000  # Frontend
curl http://localhost:8000/docs  # Backend

# Docker commands
docker-compose up -d        # Start all services
docker-compose down         # Stop all services
docker-compose logs -f      # View logs
docker-compose restart      # Restart services

# Manual commands
cd surfsense_backend && python main.py  # Start backend
cd surfsense_web && npm start           # Start frontend
celery -A celery_worker.celery_app worker  # Start worker
```

### Default Credentials

If you're using the Docker quick-start with pre-seeded data:

- **Email**: Check the seeding script or logs
- **Password**: Check the seeding script or logs

For fresh installations, you create your own account!

### Important URLs

| Service | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| API Docs | http://localhost:8000/docs |
| Flower (Tasks) | http://localhost:5555 |
| pgAdmin (DB) | http://localhost:5050 |

---

**Welcome to SurfSense!** 🎉

Start exploring your documents, chatting with AI, and collaborating with your team. If you have questions, our community is here to help!

---

**Last Updated**: February 2026

For the latest updates, visit: https://github.com/MODSetter/SurfSense
