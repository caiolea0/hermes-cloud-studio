#!/bin/bash
# =====================================================
# Hermes VM Complete Setup — Run via:
#   ssh hermes-gcp@136.115.74.69 'bash -s' < setup_vm_complete.sh
# =====================================================
set -e

echo "=== 1. AgentMemory ==="
sudo npm install -g @agentmemory/agentmemory
echo ">>> AgentMemory installed"

# Start as background service
mkdir -p ~/.hermes/logs
nohup agentmemory > ~/.hermes/logs/agentmemory.log 2>&1 &
sleep 3
curl -s http://localhost:3111/agentmemory/health && echo " OK" || echo " Pending..."

echo ""
echo "=== 2. Agent Zero — Ollama Config ==="
cd /home/hermes-gcp/agent-zero

# Create .env for Ollama (NO API keys needed)
cat > .env << 'EOF'
# Agent Zero — Local Ollama (zero cost)
# No API keys required — all models run locally via Ollama

# Web UI
WEB_UI_HOST=0.0.0.0
WEB_UI_PORT=50080

# Ollama runs on localhost:11434 (already active)
# Models: qwen3:8b (chat), qwen3:4b (utility)
# Embeddings: HuggingFace sentence-transformers (local)
EOF

echo ">>> .env created (Ollama, no API keys)"

# Install Python deps in venv
echo ""
echo "=== 3. Agent Zero — Python Dependencies ==="
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
echo ">>> Python deps installed"

# Install playwright browsers
playwright install chromium
echo ">>> Playwright browsers installed"

echo ""
echo "=== 4. Test Ollama models ==="
ollama list
echo ""
echo "Testing qwen3:8b..."
echo "Say hello in one sentence" | ollama run qwen3:8b --nowordwrap 2>/dev/null | head -3
echo ""

echo "=== 5. Start Agent Zero ==="
# Run Agent Zero (non-Docker, direct Python)
cd /home/hermes-gcp/agent-zero
source venv/bin/activate
nohup python3 run_ui.py > ~/.hermes/logs/agent_zero.log 2>&1 &
sleep 5
echo "Agent Zero PID: $(pgrep -f run_ui.py || echo 'not started')"

echo ""
echo "========================================="
echo "  SETUP COMPLETE"
echo "========================================="
echo ""
echo "Services:"
echo "  AgentMemory:  http://localhost:3111  (health: /agentmemory/health)"
echo "  Agent Zero:   http://136.115.74.69:50080"
echo "  Ollama:       http://localhost:11434"
echo ""
echo "Models (all local, zero cost):"
echo "  Chat:      qwen3:8b  (8.2B params, ~5GB RAM)"
echo "  Utility:   qwen3:4b  (4B params, ~2.5GB RAM)"
echo "  Embedding: sentence-transformers/all-MiniLM-L6-v2 (local)"
echo ""
echo "To access Agent Zero UI from your PC:"
echo "  http://136.115.74.69:50080"
