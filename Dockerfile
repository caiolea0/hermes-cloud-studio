# Hermes 2.0 — imagem de produção (VPS Contabo, geronimo-net)
# Roda hermes_api_v2.py (API :8420) e daemon/orchestrator.py. NÃO inclui server.py (PC-only, aposentado).
# LinkedIn FROZEN: patchright NÃO entra (só está em linkedin/requirements.txt, não instalado aqui).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    HERMES_HOME=/var/lib/hermes

WORKDIR /app

# deps de sistema p/ psutil/crypto/httpx + curl p/ healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential libssl-dev libffi-dev curl \
    && rm -rf /var/lib/apt/lists/*

# instala deps Python — remove Windows-only (pystray/pywebview) e dev-only (pytest*) que não rodam/precisam no container Linux
COPY requirements.txt ./
RUN grep -viE '^(pystray|pywebview|pytest)' requirements.txt > requirements.docker.txt \
    && pip install -U pip \
    && pip install -r requirements.docker.txt

COPY . .

RUN mkdir -p /var/lib/hermes/data /var/lib/hermes/logs

EXPOSE 8420

HEALTHCHECK --interval=30s --timeout=8s --start-period=25s --retries=3 \
  CMD curl -fsS http://localhost:8420/api/_ping || exit 1

# default = API. O daemon sobrescreve o command no docker-compose.
CMD ["python", "-m", "uvicorn", "hermes_api_v2:app", "--host", "0.0.0.0", "--port", "8420"]
