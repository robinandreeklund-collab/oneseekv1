# Testing SurfSense Without Database and Authentication

This guide explains how to run SurfSense in a testing/development mode without requiring PostgreSQL database or authentication, making it easier to test the platform with local LLMs.

## Quick Start

### 1. Configure Environment Variables

Create a `.env` file in the `surfsense_backend` directory with minimal configuration:

```bash
# Disable database requirement
DATABASE_REQUIRED=FALSE

# Disable authentication requirement  
AUTH_REQUIRED=FALSE

# Minimal required settings
SECRET_KEY=test-secret-key-change-in-production
NEXT_FRONTEND_URL=http://localhost:3000

# Embedding model (local, no API key needed)
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2

# File parser (local, no API key needed)
ETL_SERVICE=DOCLING

# Optional: Redis (if you want to test with Celery)
# CELERY_BROKER_URL=redis://localhost:6379/0
# CELERY_RESULT_BACKEND=redis://localhost:6379/0
```

### 2. Running with Local LLM via vLLM

#### Install and Start vLLM Server

```bash
# Install vLLM
pip install vllm

# Start vLLM server with OpenAI-compatible API
python -m vllm.entrypoints.openai.api_server \
  --model meta-llama/Llama-2-7b-chat-hf \
  --port 8001 \
  --host 0.0.0.0
```

**Note**: Using port 8001 to avoid conflict with SurfSense backend on port 8000.

#### Alternative: Use Ollama

```bash
# Install and start Ollama
curl https://ollama.ai/install.sh | sh
ollama serve

# Pull a model
ollama pull llama2
```

### 3. Start SurfSense Backend

```bash
cd surfsense_backend
python main.py
```

The backend will start without requiring database connection or authentication.

## Configuring Local LLM in SurfSense

Since the database is disabled, you'll need to configure LLMs using the global configuration file.

### Option 1: Using Global LLM Config (Recommended for Testing)

Create or edit `surfsense_backend/app/config/global_llm_config.yaml`:

```yaml
# Global LLM configurations for testing
global_llm_configs:
  # vLLM configuration
  - id: -1
    name: "Local vLLM"
    description: "Local LLM via vLLM"
    provider: "OLLAMA"  # OLLAMA provider works with OpenAI-compatible endpoints
    model_name: "meta-llama/Llama-2-7b-chat-hf"
    api_base: "http://localhost:8001/v1"
    api_key: "EMPTY"  # vLLM doesn't require auth by default
    
  # Ollama configuration
  - id: -2
    name: "Local Ollama"
    description: "Local LLM via Ollama"
    provider: "OLLAMA"
    model_name: "llama2"
    api_base: "http://localhost:11434"
    api_key: "EMPTY"

# Router settings for Auto mode (optional)
router_settings:
  routing_strategy: "usage-based-routing"
  num_retries: 3
  allowed_fails: 3
  cooldown_time: 60
```

### Option 2: Using Environment Variables (Quick Test)

For a quick test, you can also set a default LLM via environment:

```bash
# In your .env file, add:
DEFAULT_LLM_PROVIDER=OLLAMA
DEFAULT_LLM_MODEL=llama2
DEFAULT_LLM_API_BASE=http://localhost:11434
```

## What Works in Testing Mode

### ✅ Available Features

- **Chat Interface**: Full chat functionality with streaming responses
- **LLM Integration**: Connect to local LLMs via vLLM or Ollama
- **API Testing**: Test API endpoints without authentication
- **Frontend Development**: Develop and test UI components
- **LLM Provider Testing**: Verify LiteLLM configurations

### ❌ Unavailable Features (Requires Database)

- **Document Storage**: Cannot upload or store documents
- **RAG (Retrieval-Augmented Generation)**: No vector search capability
- **Search Spaces**: No workspace management
- **User Management**: No user registration or profile management
- **Connectors**: Cannot configure external data sources
- **Chat History**: Chat sessions are not persisted
- **RBAC**: No role-based access control

## Testing the Chat Interface

### Using cURL

```bash
# Test chat endpoint (no auth required when AUTH_REQUIRED=FALSE)
curl -X POST http://localhost:8000/api/v1/new_chat \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {
        "role": "user",
        "content": "Hello, how are you?"
      }
    ],
    "search_space_id": 0,
    "llm_config_id": -1
  }'
```

### Using the Web Interface

1. Start the frontend:
```bash
cd surfsense_web
npm install
npm run dev
```

2. Open http://localhost:3000
3. You can access the chat interface directly without login
4. Select your local LLM configuration

## Advanced Configuration

### Custom LLM Provider

If you have a custom OpenAI-compatible endpoint:

```yaml
global_llm_configs:
  - id: -3
    name: "Custom Local LLM"
    description: "Custom OpenAI-compatible endpoint"
    provider: "CUSTOM"
    custom_provider: "openai"
    model_name: "your-model-name"
    api_base: "http://your-server:port/v1"
    api_key: "your-api-key-if-required"
    litellm_params:
      temperature: 0.7
      max_tokens: 2048
```

### Enabling Specific Features

You can selectively enable features even without database:

```bash
# Enable Redis for caching (optional)
REDIS_APP_URL=redis://localhost:6379/0

# Enable specific services
TTS_SERVICE=local/kokoro  # Text-to-speech
STT_SERVICE=local/base    # Speech-to-text (Whisper)
```

## Troubleshooting

### Issue: "Database connection error"

**Solution**: Ensure `DATABASE_REQUIRED=FALSE` is set in your `.env` file.

### Issue: "Authentication required"

**Solution**: Ensure `AUTH_REQUIRED=FALSE` is set in your `.env` file.

### Issue: "Cannot find LLM configuration"

**Solution**: Check that your `global_llm_config.yaml` file exists and contains valid configuration. The file should be at `surfsense_backend/app/config/global_llm_config.yaml`.

### Issue: vLLM connection error

**Solution**: 
1. Verify vLLM server is running: `curl http://localhost:8001/v1/models`
2. Check the API base URL in your configuration
3. Ensure there's no firewall blocking the connection

### Issue: Model loading fails

**Solution**: 
- Ensure you have enough GPU/CPU memory for your model
- For vLLM, check the vLLM server logs for errors
- Try a smaller model like `llama-2-7b` instead of larger models

## Production Deployment

**⚠️ IMPORTANT**: The testing mode (DATABASE_REQUIRED=FALSE and AUTH_REQUIRED=FALSE) is **ONLY** for development and testing purposes. 

For production deployment:
1. Always use a proper PostgreSQL database
2. Enable authentication (AUTH_REQUIRED=TRUE)
3. Use secure SECRET_KEY
4. Configure proper OAuth or strong password policies
5. Enable HTTPS
6. Set up proper CORS policies

## Additional Resources

- [vLLM Documentation](https://docs.vllm.ai/)
- [Ollama Documentation](https://ollama.ai/docs)
- [LiteLLM Documentation](https://docs.litellm.ai/)
- [SurfSense Full Documentation](https://www.surfsense.com/docs/)

## Support

If you encounter issues:
1. Check the [GitHub Issues](https://github.com/MODSetter/SurfSense/issues)
2. Join the [Discord Community](https://discord.gg/ejRNvftDp9)
3. Review the [Contributing Guide](CONTRIBUTING.md)
