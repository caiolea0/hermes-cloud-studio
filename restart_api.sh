#!/bin/bash
pkill -f hermes_api.py || true
sleep 2
cd /home/hermes-gcp/.hermes/scripts
nohup python3 hermes_api.py > /home/hermes-gcp/.hermes/logs/api.log 2>&1 &
echo "API restarted PID: $!"
sleep 1
curl -s http://localhost:8420/api/hermes/status | head -c 200
