#!/bin/bash
ls -la /home/hermes-gcp/.local/bin/google-chrome* 2>/dev/null
echo '---'
for p in /usr/bin/google-chrome /usr/bin/google-chrome-stable /opt/google/chrome/chrome /snap/bin/google-chrome; do
    if [ -x "$p" ]; then echo "FOUND: $p"; fi
done
echo '---'
/home/hermes-gcp/.local/bin/google-chrome --version 2>&1 | head -3 || echo "no chrome via .local/bin"
