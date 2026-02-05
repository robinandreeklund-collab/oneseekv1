# SurfSense Documentation Overview

Welcome to SurfSense! This document helps you navigate the documentation based on your needs.

## 📚 Documentation Guide

### Choose Your Path

#### 👤 **I just installed SurfSense and want to start using it**
→ **[GETTING_STARTED.md](GETTING_STARTED.md)** ⭐ **START HERE**
- Create your account
- Log in to the platform
- First-time setup
- Upload documents and start chatting
- Troubleshoot common user issues

#### 🚀 **I want to try SurfSense quickly**
→ **[README.md](README.md)** - Quick Start section
- Use Docker one-liner
- 5-minute setup
- Pre-configured environment

#### 🔧 **I want to install SurfSense properly**
→ **[INSTALLATION.md](INSTALLATION.md)**
- Complete installation guide
- PostgreSQL + pgvector setup
- Redis configuration
- Production deployment
- Troubleshooting

#### 🧪 **I want to test with local LLMs (no database)**
→ **[TESTING_WITHOUT_DATABASE.md](TESTING_WITHOUT_DATABASE.md)**
- Testing mode setup
- vLLM / Ollama configuration
- No authentication needed
- Quick development setup

#### 🔍 **I want to understand the architecture**
→ **[IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md)**
- Technical analysis
- Architecture details
- Implementation notes
- Platform capabilities

---

## 📖 Documentation Contents

### README.md
**Quick start and overview**
- Project introduction
- Key features
- Quick start options (Docker, Testing mode)
- Installation options overview
- Tech stack overview

### GETTING_STARTED.md ⭐
**User guide for new users (500+ lines)**

**Covers:**
- How to access the platform
- Creating an account (LOCAL and Google OAuth)
- Logging in for the first time
- First-time setup walkthrough
- Creating search spaces
- Configuring LLM settings
- Uploading documents
- Starting your first chat
- Troubleshooting user issues

**Best for:**
- New users after installation
- First-time platform access
- Understanding basic features
- Getting productive quickly

### INSTALLATION.md
**Complete installation guide (1300+ lines)**

**Covers:**
- System prerequisites
- PostgreSQL installation (Linux, macOS, Windows)
- pgvector extension setup
- Redis installation and configuration
- Backend setup (Python, dependencies, Celery)
- Frontend setup (Node.js, Next.js)
- Environment variables (complete reference)
- Database management (backup, restore, migrations)
- Production deployment (systemd, nginx, security)
- Troubleshooting (10+ common issues)

**Best for:**
- Production deployments
- Manual installations
- Database setup and configuration
- Complete control over setup

### TESTING_WITHOUT_DATABASE.md
**Testing mode guide (260+ lines)**

**Covers:**
- Testing without PostgreSQL
- Testing without authentication
- Local LLM setup (vLLM, Ollama)
- Quick configuration
- Available features vs. limitations
- Development workflow

**Best for:**
- Quick testing
- LLM integration testing
- Development without infrastructure
- Frontend development

### IMPLEMENTATION_SUMMARY.md
**Technical documentation (400+ lines)**

**Covers:**
- Platform architecture analysis
- Component breakdown
- Authentication system details
- Database schema overview
- LLM integration architecture
- Implementation notes
- Code changes summary

**Best for:**
- Understanding the codebase
- Technical deep-dive
- Contributing to the project
- Architecture decisions

---

## 🎯 Quick Navigation

### By Use Case

| Use Case | Guide | Time to Complete |
|----------|-------|------------------|
| **I just installed, now what?** | **GETTING_STARTED.md** ⭐ | **5-10 minutes** |
| Quick evaluation | README.md (Docker) | 5 minutes |
| Testing with local LLMs | TESTING_WITHOUT_DATABASE.md | 15 minutes |
| Development setup | INSTALLATION.md (Manual) | 1-2 hours |
| Production deployment | INSTALLATION.md (Production) | 2-4 hours |
| Understanding architecture | IMPLEMENTATION_SUMMARY.md | - |

### By Stage

| Stage | Documentation |
|-------|---------------|
| **Before Installation** | README.md → Installation Options |
| **During Installation** | INSTALLATION.md |
| **After Installation** | **GETTING_STARTED.md** ⭐ |
| **Using the Platform** | GETTING_STARTED.md |
| **Development/Testing** | TESTING_WITHOUT_DATABASE.md |
| **Production Deployment** | INSTALLATION.md → Production |
| **Technical Deep-Dive** | IMPLEMENTATION_SUMMARY.md |

### By Component

| Component | Documentation |
|-----------|---------------|
| **Account Creation** | **GETTING_STARTED.md** → Creating an Account |
| **Login** | **GETTING_STARTED.md** → Logging In |
| **First-Time Setup** | **GETTING_STARTED.md** → First Time Setup |
| **Using the Platform** | **GETTING_STARTED.md** → Using SurfSense |
| PostgreSQL | INSTALLATION.md → PostgreSQL Setup |
| pgvector | INSTALLATION.md → PostgreSQL Setup |
| Redis | INSTALLATION.md → Redis Setup |
| Backend | INSTALLATION.md → Backend Setup |
| Frontend | INSTALLATION.md → Frontend Setup |
| Database Management | INSTALLATION.md → Database Management |
| Production | INSTALLATION.md → Production Deployment |
| Local LLMs | TESTING_WITHOUT_DATABASE.md |
| Configuration | INSTALLATION.md → Configuration |
| Troubleshooting | INSTALLATION.md or GETTING_STARTED.md → Troubleshooting |

### By Operating System

| OS | Installation Guide |
|----|-------------------|
| Linux (Ubuntu/Debian) | INSTALLATION.md (all sections) |
| macOS | INSTALLATION.md (all sections) |
| Windows | INSTALLATION.md (WSL2 recommended) |
| Docker | README.md or INSTALLATION.md |

---

## 🔗 External Resources

- **Official Website**: https://www.surfsense.com/
- **Documentation**: https://www.surfsense.com/docs/
- **GitHub**: https://github.com/MODSetter/SurfSense
- **Discord**: https://discord.gg/ejRNvftDp9
- **Reddit**: https://www.reddit.com/r/SurfSense/

---

## 📝 Additional Files

### Configuration Examples
- **`.env.example`** - Environment variable template
- **`global_llm_config.example.yaml`** - LLM configuration template
- **`docker-compose.yml`** - Docker Compose setup

### Setup Scripts
- **`quick-start-testing.sh`** - Automated testing mode setup

---

## 🆘 Getting Help

### Quick Answers
1. Check relevant documentation above
2. Search [GitHub Issues](https://github.com/MODSetter/SurfSense/issues)
3. Review [Troubleshooting](INSTALLATION.md#troubleshooting) section

### Community Support
- **Discord**: [Join here](https://discord.gg/ejRNvftDp9)
- **Reddit**: [r/SurfSense](https://www.reddit.com/r/SurfSense/)
- **GitHub Discussions**: [Ask questions](https://github.com/MODSetter/SurfSense/discussions)

### Report Issues
- **Bugs**: [GitHub Issues](https://github.com/MODSetter/SurfSense/issues/new)
- **Features**: [GitHub Discussions](https://github.com/MODSetter/SurfSense/discussions)

---

## 🔄 Documentation Updates

This documentation is regularly updated. Last updated: **February 2026**

For the latest version, visit: https://github.com/MODSetter/SurfSense

---

## 📄 License

SurfSense is licensed under the [Apache License 2.0](LICENSE).

