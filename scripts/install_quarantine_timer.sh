#!/bin/bash
# F.4.4 C2 — Install hermes-skill-quarantine systemd user timer (idempotent).
#
# Usage (VM):
#   bash ~/hermes-cloud-studio/scripts/install_quarantine_timer.sh
#
# Creates:
#   ~/.config/systemd/user/hermes-skill-quarantine.service
#   ~/.config/systemd/user/hermes-skill-quarantine.timer
# Enables + starts the timer (hourly OnCalendar=hourly + Persistent=true).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
DB_PATH="${HERMES_DB_PATH:-$HERMES_HOME/data/command_center.db}"
SKILLS_DIR="${HERMES_SKILLS_DIR:-$HERMES_HOME/skills}"
SYSTEMD_DIR="$HOME/.config/systemd/user"
PYTHON="${HERMES_PYTHON:-python3}"

log() { echo "[install_quarantine_timer] $*"; }

mkdir -p "$SYSTEMD_DIR"

log "Writing hermes-skill-quarantine.service → $SYSTEMD_DIR/"
cat > "$SYSTEMD_DIR/hermes-skill-quarantine.service" << EOF
[Unit]
Description=Hermes Skill Quarantine Cron (F.4.4 C2)
After=network.target

[Service]
Type=oneshot
WorkingDirectory=$SCRIPT_DIR
ExecStart=$PYTHON $SCRIPT_DIR/quarantine_skills.py
Environment="HERMES_DB_PATH=$DB_PATH"
Environment="HERMES_SKILLS_DIR=$SKILLS_DIR"
Environment="HERMES_HOME=$HERMES_HOME"
StandardOutput=journal
StandardError=journal
EOF

log "Writing hermes-skill-quarantine.timer → $SYSTEMD_DIR/"
cat > "$SYSTEMD_DIR/hermes-skill-quarantine.timer" << EOF
[Unit]
Description=Hermes Skill Quarantine Cron — hourly (F.4.4 C2)

[Timer]
OnCalendar=hourly
Persistent=true
RandomizedDelaySec=60

[Install]
WantedBy=timers.target
EOF

log "Reloading systemd user daemon..."
systemctl --user daemon-reload

log "Enabling + starting timer..."
systemctl --user enable --now hermes-skill-quarantine.timer

log "Status:"
systemctl --user status hermes-skill-quarantine.timer --no-pager || true
systemctl --user list-timers hermes-skill-quarantine.timer --no-pager || true

log "Install complete. Next firing:"
systemctl --user list-timers hermes-skill-quarantine.timer --no-pager 2>&1 | grep -E 'NEXT|hermes' || true
