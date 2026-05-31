#!/bin/bash
# Hermes VM Setup — AgentMemory + Agent Zero
# Run: ssh hermes-gcp@136.115.74.69 'bash -s' < setup_vm.sh

set -e
echo "=== Hermes VM Setup ==="

# --- 1. AgentMemory ---
echo ""
echo ">>> Installing AgentMemory..."
npm install -g @agentmemory/agentmemory

echo ">>> Creating AgentMemory systemd service..."
sudo tee /etc/systemd/system/agentmemory.service > /dev/null <<'EOF'
[Unit]
Description=AgentMemory Server
After=network.target

[Service]
Type=simple
User=hermes-gcp
Environment=NODE_ENV=production
ExecStart=/usr/bin/agentmemory
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable agentmemory
sudo systemctl start agentmemory
echo ">>> AgentMemory service started on port 3111"
sleep 2
curl -s http://localhost:3111/agentmemory/health || echo "Health check pending..."

# --- 2. Agent Zero (Docker) ---
echo ""
echo ">>> Setting up Agent Zero..."
cd /home/hermes-gcp

if [ ! -d "agent-zero" ]; then
    git clone https://github.com/agent0ai/agent-zero.git
fi
cd agent-zero

# Create .env with Anthropic key (user must fill in)
if [ ! -f ".env" ]; then
    cat > .env <<'EOF'
# Agent Zero — LLM Configuration
# Fill in your API key:
API_KEY_ANTHROPIC=
CHAT_MODEL_NAME=claude-sonnet-4-20250514
UTILITY_MODEL_NAME=claude-haiku-4-5-20251001

# AgentMemory integration (local server)
AGENTMEMORY_URL=http://localhost:3111
EOF
    echo ">>> Created .env — FILL IN API_KEY_ANTHROPIC before starting"
fi

echo ">>> Pulling Agent Zero Docker image..."
docker compose pull 2>/dev/null || docker-compose pull 2>/dev/null || echo "Pull failed — will build on first run"

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Next steps:"
echo "  1. Edit /home/hermes-gcp/agent-zero/.env — add API_KEY_ANTHROPIC"
echo "  2. Start Agent Zero: cd /home/hermes-gcp/agent-zero && docker compose up -d"
echo "  3. Access Agent Zero UI: http://136.115.74.69:80"
echo "  4. AgentMemory health: curl http://localhost:3111/agentmemory/health"
echo ""
echo "AgentMemory status:"
systemctl status agentmemory --no-pager | head -5
