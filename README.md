<p align="center">
  <h1 align="center">Hermes Cloud Studio</h1>
  <p align="center">
    <strong>Autonomous B2B prospecting and digital marketing command center</strong>
  </p>
  <p align="center">
    <img src="https://img.shields.io/badge/python-3.11+-blue?logo=python&logoColor=white" alt="Python">
    <img src="https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white" alt="FastAPI">
    <img src="https://img.shields.io/badge/SQLite-WAL-003B57?logo=sqlite&logoColor=white" alt="SQLite">
    <img src="https://img.shields.io/badge/Playwright-stealth-2EAD33?logo=playwright&logoColor=white" alt="Playwright">
    <img src="https://img.shields.io/badge/Tauri-2.0-FFC131?logo=tauri&logoColor=white" alt="Tauri">
    <img src="https://img.shields.io/badge/license-private-red" alt="License">
  </p>
</p>

---

## Overview

Hermes Cloud Studio is a full-stack autonomous prospecting system that discovers local businesses, audits their digital presence, scores opportunities, and generates personalized outreach messages — all running 24/7 with minimal human intervention.

Built for a freelance designer and digital strategist based in Cuiaba, MT, Brazil, it automates the entire B2B sales pipeline: from finding businesses on Google Maps to sending personalized WhatsApp/email proposals.

---

## Architecture

```
+----- WINDOWS PC (Dashboard + Orchestrator) ---------------------+
|                                                                  |
|  Hermes Desktop App (pywebview + pystray)                       |
|  +-- System Tray Icon (green/yellow/red status)                 |
|  +-- SOCKS5 Proxy (127.0.0.1:1081)                             |
|  +-- SSH Tunnel (reverse forward to VM)                         |
|  +-- Dashboard Server (FastAPI :8500)                           |
|      +-- Sync Loop (pulls VM data every 60s)                   |
|      +-- Local SQLite (hermes_local.db)                        |
|      +-- Photo Cache (proxy + local storage)                   |
|      +-- AI Integration (Agent Zero + Claude CLI fallback)     |
|                                                                  |
|  Dashboard Frontend (vanilla HTML/CSS/JS)                       |
|  +-- Prospect cards (photo, score, stage, actions)              |
|  +-- Task board (Kanban: pending > running > completed)         |
|  +-- Activity feed (timeline)                                   |
|  +-- Pipeline builder (create + execute automation flows)       |
|  +-- Scraper controls (start/stop, logs, history)               |
|  +-- Stats dashboard (by stage, city, category, trends)         |
|  +-- Work queue (prioritized daily actions)                     |
|                                                                  |
+------------------------------------------------------------------+
              | SSH + Proxy |         | HTTP API |
+------ GCP VM (24/7 Execution Engine) ---------------------------+
|                                                                  |
|  Hermes API Bridge (FastAPI :8420)                              |
|  +-- /api/prospects (CRUD, filtering, scoring)                  |
|  +-- /api/tasks (dispatch to AI agents)                         |
|  +-- /api/activities (event log)                                |
|  +-- /api/scraper/{status,start,stop,history}                   |
|  +-- /api/audit/{start,status,prospect}                         |
|  +-- /api/hermes/{status,skills}                                |
|  +-- /api/stats (pipeline metrics)                              |
|                                                                  |
|  Discovery Scrapers                                              |
|  +-- night_scraper.py (Google Places API, 111 categories)       |
|  +-- gosom_scraper.py (Docker-based free alternative)           |
|  +-- 16 cities in Mato Grosso state                             |
|                                                                  |
|  Hermes Agent v0.14.0 (Autonomous AI Agent)                     |
|  +-- 85+ skills out-of-box                                      |
|  +-- OpenRouter (free tier, model rotation)                     |
|  +-- Ollama local fallback (qwen3:14b, phi4-mini)               |
|  +-- Telegram gateway for approvals                             |
|  +-- Persistent memory system                                   |
|                                                                  |
+------------------------------------------------------------------+
              |              |              |
+------ EXTERNAL SERVICES ----------------------------------------+
|                                                                  |
|  LinkedIn (Patchright anti-detection)                           |
|  +-- 11 stealth JS patches (webdriver, canvas, WebGL, RTC)     |
|  +-- Human behavior simulation (Bezier mouse, typing, scroll)  |
|  +-- Rate limiter with 14-day warm-up                           |
|  +-- Session persistence + profile reuse                        |
|                                                                  |
|  Google Maps/Places API (business discovery)                    |
|  Telegram Bot (status, approvals, reports)                      |
|  Gmail SMTP (pipeline reports)                                  |
|  OpenRouter (free LLM tier: Nemotron, DeepSeek, Gemma)          |
|                                                                  |
+------------------------------------------------------------------+
```

---

## Features

### Discovery & Scraping
- Automated Google Maps scraping (111 business categories x 16 cities)
- Dual scraper engine: Google Places API + Docker-based gosom (free)
- Auto-deduplication by name, phone, and place_id
- Resume capability with checkpoint files
- Photo extraction and local caching

### Digital Audit
- Website health check (SSL, mobile viewport, response time)
- Social media discovery (Instagram, Facebook handle guessing)
- Google rating and review analysis
- Opportunity scoring (0-100) based on digital presence gaps
- Category-aware scoring (restaurants, clinics, salons score higher)

### Outreach Generation
- Personalized WhatsApp messages by category and audit results
- Professional email templates with dynamic service recommendations
- 8 service types mapped to 19 business categories
- Template + AI hybrid generation (local templates + Claude refinement)

### LinkedIn Automation
- Patchright/Playwright stealth browser with 11 anti-detection patches
- Human behavior simulation (Bezier mouse curves, typing patterns, scroll momentum)
- Rate limiter with SQLite persistence and 14-day warm-up ramp
- Profile viewer with search, visit, and data extraction
- Session persistence across restarts

### Dashboard
- Dark mode glassmorphism UI (Higgsfield-inspired)
- Prospect card grid with photo, rating, score, stage
- Pipeline builder with template system
- Scraper control panel with real-time logs
- Work queue with prioritized daily actions
- Activity timeline with filtering

### Desktop App
- Native Windows app via pywebview + pystray
- System tray icon with color-coded status
- Built-in SOCKS5 proxy with authentication
- SSH tunnel with auto-reconnect watchdog
- One-click launch for entire stack

---

## Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Frontend** | Vanilla HTML/CSS/JS | Dashboard UI |
| **Desktop** | pywebview + pystray | Native window + system tray |
| **PC Backend** | FastAPI (Python) | Local API, sync, photo proxy |
| **VM Backend** | FastAPI (Python) | CRUD API, scraper control |
| **Database** | SQLite (WAL mode) | Prospects, tasks, activities |
| **Scraping** | Google Places API, gosom Docker | Business discovery |
| **Browser Automation** | Patchright/Playwright | LinkedIn stealth |
| **AI Agent** | Hermes Agent v0.14.0 | Autonomous task execution |
| **LLM (Cloud)** | OpenRouter free tier | Nemotron, DeepSeek, Gemma |
| **LLM (Local)** | Ollama | qwen3:14b, phi4-mini |
| **Communication** | Telegram Bot API | Approvals, alerts |
| **Infrastructure** | GCP e2-standard-4 | 24/7 VM (4 vCPU, 16GB RAM) |

---

## Quick Start

### Prerequisites
- Python 3.11+
- Windows 10/11 (for desktop app)
- SSH key configured for VM access

### Installation

```bash
# Clone the repository
git clone https://github.com/caiolea0/hermes-cloud-studio.git
cd hermes-cloud-studio

# Install dependencies
pip install fastapi uvicorn httpx python-dotenv pystray pywebview Pillow

# Configure environment
cp .env.example .env
# Edit .env with your credentials
```

### Running

```bash
# Option 1: Dashboard server only
python server.py

# Option 2: Full desktop app (proxy + tunnel + server + webview)
python hermes_desktop.py
```

- Dashboard: http://localhost:8500
- API Docs: http://localhost:8500/docs
- VM API: http://YOUR_VM_IP:8420/docs

---

## Project Structure

```
hermes-cloud-studio/
+-- server.py                  # PC: FastAPI dashboard backend (:8500)
+-- hermes_desktop.py          # PC: Desktop app (tray + proxy + tunnel)
+-- hermes_api_v2.py           # VM: API bridge (:8420)
+-- night_scraper.py           # VM: Google Places scraper
+-- gosom_scraper.py           # VM: Docker-based free scraper
+-- dashboard/
|   +-- index.html             # Dashboard frontend
+-- linkedin/
|   +-- config.py              # Rate limits, proxy, browser config
|   +-- viewer.py              # Profile visitor with search + extraction
|   +-- stealth.py             # 11 anti-detection JS patches
|   +-- human.py               # Mouse, typing, scroll simulation
|   +-- limiter.py             # Rate limiter with warm-up tracking
+-- scripts/
|   +-- pipeline.py            # Master orchestrator
|   +-- web_audit.py           # Website audit engine
|   +-- outreach_generator.py  # Message generation by category
|   +-- google_maps_scraper.py # Legacy scraper
+-- app/                       # Tauri desktop app scaffold
+-- docs/
|   +-- HERMES-PROJECT-CONTEXT.md  # Full project specification
+-- .env.example               # Environment template
+-- .gitignore
```

---

## Pipeline Stages

```
Discovery          Qualification         Audit              Outreach
+-----------+     +-------------+     +-----------+     +-------------+
| Google    |     | Dedup by    |     | Website   |     | WhatsApp    |
| Maps scan | --> | name+phone  | --> | SSL/mobile| --> | message     |
| 16 cities |     | Score 0-100 |     | Social    |     | Email       |
| 111 cats  |     | Categorize  |     | Rating    |     | Personalized|
+-----------+     +-------------+     +-----------+     +-------------+
     |                  |                   |                  |
     v                  v                   v                  v
  discovered        qualified            audited           outreach
  (raw data)       (scored+dedup)    (audit summary)    (ready to send)
```

---

## Model Rotation Strategy

| Task Type | Model | Provider | Reason |
|-----------|-------|----------|--------|
| Posts, personalized messages | deepseek/deepseek-v4-flash:free | OpenRouter | Best writing quality |
| Comments, quick summaries | minimax/minimax-m2.5:free | OpenRouter | Saves DeepSeek quota |
| Image/screenshot analysis | google/gemma-4-31b-it:free | OpenRouter | Only free vision model |
| Profile classification | qwen3:8b | Ollama local | Unlimited, fast |
| General fallback | qwen3:14b | Ollama local | When cloud limits hit |
| Default chat | nvidia/nemotron-3-super-120b-a12b:free | OpenRouter | Good balance |

Free tier limits: 20 req/min, 200 req/day per model. With rotation across 3+ models: ~600+ req/day effective.

---

## Security

- All credentials stored in `.env` (gitignored)
- SSH tunnel with `StrictHostKeyChecking=accept-new`
- SOCKS5 proxy with username/password authentication
- LinkedIn anti-detection with 11 browser stealth patches
- Rate limiting with warm-up to avoid account flags
- Token-based API authentication

---

## Roadmap

- [x] Google Maps discovery (night_scraper + gosom_scraper)
- [x] Web audit engine (SSL, mobile, speed, social)
- [x] Outreach message generation (WhatsApp + email)
- [x] LinkedIn stealth browser (Patchright + human simulation)
- [x] Dashboard with prospect management
- [x] Desktop app with system tray
- [x] VM API bridge with sync
- [x] Pipeline builder and executor
- [ ] Dashboard authentication
- [ ] WebSocket real-time updates
- [ ] LinkedIn Agent skills (post, research, connect, engage)
- [ ] Telegram-Claude Code bridge
- [ ] Cloudflare Tunnel for mobile access
- [ ] Weekly mission planner

---

## Author

**Caio Leao** — Designer & Digital Strategist
- Cuiaba, MT, Brazil
- [cleao.mkt@gmail.com](mailto:cleao.mkt@gmail.com)
