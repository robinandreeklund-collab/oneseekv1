#!/bin/bash

# SurfSense Quick Start Script for Testing with Local LLMs
# This script sets up SurfSense in testing mode (no database/auth required)

set -e  # Exit on error

echo "🚀 SurfSense Quick Start - Testing Mode"
echo "========================================"
echo ""

# Check if we're in the right directory
if [ ! -d "surfsense_backend" ]; then
    echo "❌ Error: Please run this script from the root of the SurfSense repository"
    exit 1
fi

# Create minimal .env file
echo "📝 Creating minimal .env configuration..."
cat > surfsense_backend/.env << 'EOF'
# Testing mode - no database or authentication required
DATABASE_REQUIRED=FALSE
AUTH_REQUIRED=FALSE

# Minimal required settings
SECRET_KEY=test-secret-key-change-in-production
NEXT_FRONTEND_URL=http://localhost:3000

# Local embedding model (no API key needed)
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2

# Local file parser (no API key needed)
ETL_SERVICE=DOCLING

# Optional: Enable if you have Redis running
# CELERY_BROKER_URL=redis://localhost:6379/0
# CELERY_RESULT_BACKEND=redis://localhost:6379/0
EOF

echo "✅ Configuration file created at surfsense_backend/.env"
echo ""

# Copy example LLM config if it doesn't exist
if [ ! -f "surfsense_backend/app/config/global_llm_config.yaml" ]; then
    echo "📝 Creating example LLM configuration..."
    mkdir -p surfsense_backend/app/config
    
    cat > surfsense_backend/app/config/global_llm_config.yaml << 'EOF'
global_llm_configs:
  # Ollama configuration (recommended for local testing)
  - id: -1
    name: "Local Ollama (Llama2)"
    description: "Local LLM via Ollama"
    provider: "OLLAMA"
    model_name: "llama2"
    api_base: "http://localhost:11434"
    api_key: "EMPTY"
    system_instructions: "You are a helpful AI assistant."
    citations_enabled: false

router_settings:
  routing_strategy: "usage-based-routing"
  num_retries: 3
  allowed_fails: 3
  cooldown_time: 60
EOF
    
    echo "✅ LLM configuration created at surfsense_backend/app/config/global_llm_config.yaml"
else
    echo "ℹ️  Using existing LLM configuration"
fi

echo ""
echo "🎯 Next Steps:"
echo "=============="
echo ""
echo "1. Start your local LLM (choose one):"
echo ""
echo "   Option A - Ollama (Recommended):"
echo "   $ ollama serve"
echo "   $ ollama pull llama2"
echo ""
echo "   Option B - vLLM:"
echo "   $ pip install vllm"
echo "   $ python -m vllm.entrypoints.openai.api_server \\"
echo "       --model meta-llama/Llama-2-7b-chat-hf \\"
echo "       --port 8001"
echo ""
echo "2. Start SurfSense backend:"
echo "   $ cd surfsense_backend"
echo "   $ python main.py"
echo ""
echo "3. (Optional) Start frontend:"
echo "   $ cd surfsense_web"
echo "   $ npm install"
echo "   $ npm run dev"
echo ""
echo "4. Access SurfSense:"
echo "   - Backend API: http://localhost:8000"
echo "   - API Docs: http://localhost:8000/docs"
echo "   - Frontend: http://localhost:3000 (if started)"
echo ""
echo "📖 For more details, see TESTING_WITHOUT_DATABASE.md"
echo ""
