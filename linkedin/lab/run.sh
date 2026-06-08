#!/bin/bash
# Wrapper xvfb-run + lab_runner com resolucao FullHD + GLX
# Uso: ./linkedin/lab/run.sh --flow fingerprint --sites creepjs,tls_peet
set -e
cd "$(dirname "$0")/../.."
rm -f /tmp/.X*-lock 2>/dev/null || true
exec xvfb-run -a --server-args='-screen 0 1920x1080x24' python3 -m linkedin.lab.lab_runner "$@"
