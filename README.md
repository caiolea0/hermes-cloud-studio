<p align="center">
  <h1 align="center">Hermes Cloud Studio</h1>
  <p align="center">
    <strong>Autonomous B2B prospecting and digital marketing command center</strong>
  </p>
  <p align="center">
    <img src="https://img.shields.io/badge/python-3.11+-blue?logo=python&logoColor=white" alt="Python">
    <img src="https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white" alt="FastAPI">
    <img src="https://img.shields.io/badge/Tauri-2.0-FFC131?logo=tauri&logoColor=white" alt="Tauri">
    <img src="https://img.shields.io/badge/Rust-1.93-DEA584?logo=rust&logoColor=white" alt="Rust">
    <img src="https://img.shields.io/badge/SQLite-WAL-003B57?logo=sqlite&logoColor=white" alt="SQLite">
    <img src="https://img.shields.io/badge/WebSocket-realtime-4353FF?logo=websocket&logoColor=white" alt="WebSocket">
    <img src="https://img.shields.io/badge/Playwright-stealth-2EAD33?logo=playwright&logoColor=white" alt="Playwright">
    <img src="https://img.shields.io/badge/license-private-red" alt="License">
  </p>
</p>

---

## Overview

Hermes Cloud Studio is a full-stack autonomous prospecting system that discovers local businesses, audits their digital presence, scores opportunities, and generates personalized outreach — all running 24/7 with minimal human intervention.

Built for a freelance designer and digital strategist based in Cuiaba, MT, Brazil. Automates the entire B2B sales pipeline: from finding businesses on Google Maps to sending personalized WhatsApp/email proposals via AI-generated content.

### Key Capabilities

- **Discovery**: Automated Google Maps scraping across 111 categories x 16 cities
- **Audit**: Website health, social presence, SEO scoring (0-100)
- **Outreach**: AI-generated personalized proposals per category
- **LinkedIn**: Stealth automation with anti-detection and warm-up
- **Skills**: 6 LinkedIn AI skills (post generation, engagement, research)
- **Real-time**: WebSocket push updates to dashboard
- **Desktop**: Native Windows app via Tauri 2.0 with auto-restart
- **Mobile**: Telegram bridge + Cloudflare tunnel for remote access

---

## Architecture

```
┌───── WINDOWS PC (Dashboard + Orchestrator) ─────────────────────┐
│                                                                   │
│  Hermes Desktop (Tauri 2.0 / Rust)                               │
│  ├── System Tray (status: ok/recovering/cooldown)                │
│  ├── Health Monitor (10s checks, 3-restart limit, 60s cooldown)  │
│  ├── SOCKS5 Proxy (127.0.0.1:1081, invisible)                   │
│  ├── SSH Tunnel (reverse forward to VM, auto-reconnect)          │
│  └── Dashboard Server (FastAPI :8500, no terminal window)        │
│                                                                   │
│  Dashboard Server (server.py — FastAPI)                           │
│  ├── 44+ REST endpoints                                          │
│  ├── WebSocket /ws (real-time events)                            │
│  ├── Sync Loop (pulls VM data every 60s)                         │
│  ├── Auth Middleware (X-Hermes-Token)                            │
│  ├── Skills Proxy (GET/PATCH /api/hermes/skills)                 │
│  ├── Memory CRUD (GET/POST/DELETE /api/hermes/memory)            │
│  ├── Pipeline Engine (template + execute + schedule)             │
│  └── Static Files (/dashboard/ mount)                            │
│                                                                   │
│  Dashboard Frontend (vanilla HTML/CSS/JS — modular)              │
│  ├── page-dashboard — Stats, Hermes Live, Activities, Scraper    │
│  ├── page-prospects — Filtered table, bulk actions, side panel   │
│  ├── page-proposals — Outreach cards grid                        │
│  ├── page-audit — Batch audit workflow                           │
│  ├── page-pipeline — Pipeline builder + command center           │
│  ├── page-tasks — Work queue (prioritized daily)                 │
│  ├── page-skills — Hermes Agent skills (toggle, model info)      │
│  ├── page-memory — Facts, preferences, patterns (CRUD)           │
│  ├── page-missions — Weekly mission calendar + scheduler         │
│  └── page-claude — AI terminal (markdown rendering)              │
│                                                                   │
└───────────────────────────────────────────────────────────────────┘
                │ SSH + Proxy │           │ HTTP API │
┌───── GCP VM (24/7 Execution Engine) ────────────────────────────┐
│                                                                   │
│  Hermes API (FastAPI :8420)                                      │
│  ├── /api/prospects (CRUD, filtering, scoring)                   │
│  ├── /api/tasks (dispatch to AI agents)                          │
│  ├── /api/activities (event log)                                 │
│  ├── /api/scraper/{status,start,stop,history}                    │
│  ├── /api/audit/{start,status,prospect}                          │
│  ├── /api/hermes/skills (YAML-based, toggleable)                 │
│  ├── /api/pipeline/execute (multi-step flows)                    │
│  └── /api/stats (pipeline metrics)                               │
│                                                                   │
│  Discovery Scrapers                                               │
│  ├── gosom_scraper.py (Docker, Google Maps, free)                │
│  ├── night_scraper.py (Google Places API, premium)               │
│  └── 16 cities in Mato Grosso state                              │
│                                                                   │
│  Hermes Agent (Gateway Mode)                                     │
│  ├── 6 LinkedIn AI Skills (OpenRouter + Ollama)                  │
│  ├── Model Rotation (round_robin_by_task)                        │
│  ├── AgentMemory (persistent knowledge)                          │
│  └── Ollama: qwen3:8b, qwen3:14b, phi4-mini, gemma3:4b          │
│                                                                   │
│  Infrastructure                                                   │
│  ├── 96GB disk, 16GB RAM, 4 vCPU                                │
│  ├── Docker (gosom scraper)                                      │
│  └── Telegram Bot (alerts, monitoring)                            │
│                                                                   │
└───────────────────────────────────────────────────────────────────┘
                │              │              │
┌───── EXTERNAL SERVICES ─────────────────────────────────────────┐
│                                                                   │
│  LinkedIn (Patchright stealth)                                   │
│  ├── 11 anti-detection patches (webdriver, canvas, WebGL, RTC)   │
│  ├── Human simulation (Bezier mouse, typing, scroll momentum)    │
│  ├── Rate limiter + 14-day warm-up                               │
│  └── Session persistence + residential proxy                      │
│                                                                   │
│  OpenRouter (free LLM tier)                                      │
│  ├── deepseek/deepseek-chat:free (generation, analysis)          │
│  ├── nvidia/llama-3.1-nemotron-70b-instruct:free (planning)      │
│  ├── minimax/minimax-m1:free (engagement, short content)          │
│  └── Fallback chain with model rotation                           │
│                                                                   │
│  Other                                                            │
│  ├── Telegram Bot API (mobile command bridge)                    │
│  ├── Cloudflare Tunnel (HTTPS access via hermes.caioleo.com)     │
│  ├── Google Maps/Places API (business discovery)                 │
│  └── AgentMemory MCP (cross-session knowledge)                   │
│                                                                   │
└───────────────────────────────────────────────────────────────────┘
```

---

## Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Desktop** | Tauri 2.0 (Rust) | Native .exe, tray icon, process manager |
| **Frontend** | Vanilla HTML/CSS/JS | 10-page dashboard, dark glassmorphism UI |
| **PC Backend** | FastAPI + WebSocket | 44 endpoints, sync, auth, real-time |
| **VM Backend** | FastAPI | CRUD API, scraper control, skills |
| **Database** | SQLite (WAL mode) | Prospects, tasks, activities, rate limits |
| **Scraping** | gosom (Docker) + Places API | Business discovery |
| **Browser** | Patchright/Playwright | LinkedIn stealth automation |
| **AI Skills** | YAML definitions | 6 LinkedIn automation skills |
| **LLM Cloud** | OpenRouter (free) | DeepSeek, Nemotron, Minimax |
| **LLM Local** | Ollama | qwen3:8b/14b, phi4-mini |
| **Mobile** | Telegram Bot + Claude CLI | Remote command execution |
| **Tunnel** | Cloudflare | HTTPS access from anywhere |
| **Infrastructure** | GCP e2-standard-4 | 24/7 VM (4 vCPU, 16GB RAM, 96GB) |

---

## Features

### Tauri Desktop App

The desktop app launches all services invisibly (no terminal windows) and manages their lifecycle:

- **Auto-restart with safety**: Each service gets max 3 restart attempts per 60s window
- **Cooldown protection**: After 3 failures, enters 60s cooldown (prevents infinite loops)
- **Health monitoring**: Background thread checks every 10s via port probing
- **Tray status**: Tooltip shows real-time health (ok/recovering/cooldown per service)
- **Window management**: Hidden until server ready, auto-focuses on launch
- **Clean shutdown**: Kills all child processes on exit

```
Hermes.bat → hermes.exe → spawns:
  ├── python server.py     (port 8500, CREATE_NO_WINDOW)
  ├── python socks5_proxy  (port 1081, invisible)
  └── ssh tunnel           (reverse forward, invisible)
```

### Dashboard (10 Pages)

| Page | Function |
|------|----------|
| **Dashboard** | Live stats, Hermes Agent status, activities feed, scraper panel |
| **Prospects** | Filterable table with bulk actions, detail side panel |
| **Proposals** | Outreach message cards with category-based generation |
| **Audit** | Batch digital audit workflow (website, social, SEO) |
| **Pipeline** | Template builder + command center for automation flows |
| **Tasks** | Prioritized work queue with status tracking |
| **Skills** | Agent skill cards with model/provider info, active toggle |
| **Memory** | Facts, preferences, patterns — full CRUD |
| **Missions** | Weekly calendar scheduler for recurring pipelines |
| **Claude** | AI terminal with markdown rendering + provider badges |

### WebSocket Real-Time

```javascript
// Auto-reconnect WebSocket client
ws = new WebSocket('ws://localhost:8500/ws');
// Events: sync, pipeline_progress, audit_done, scraper_update
```

No polling required for live updates. Fallback to 30s/10s polling if WS disconnects.

### LinkedIn AI Skills

6 YAML-defined skills deployed to VM, each with dedicated model:

| Skill | Model | Use Case |
|-------|-------|----------|
| `linkedin-post-generator` | deepseek-chat:free | Content creation (1300 char posts) |
| `linkedin-profile-researcher` | qwen3:8b (local) | Prospect analysis, ice-breakers |
| `linkedin-connection-sender` | deepseek-chat:free | 300-char invite notes |
| `linkedin-engagement` | minimax-m1:free | Strategic comments on posts |
| `linkedin-trend-monitor` | deepseek-chat:free | Trending topics + content gaps |
| `weekly-mission-planner` | nemotron-70b:free | Weekly activity optimization |

### LinkedIn Anti-Detection

- **Patchright** (Playwright fork): patches `Runtime.enable` CDP leak
- **11 stealth patches**: webdriver, canvas fingerprint, WebGL, navigator.plugins, WebRTC, timezone, language
- **Human behavior**: Bezier curve mouse movements, variable typing speed, natural scroll momentum
- **Rate limiting**: SQLite-tracked daily/weekly caps with 14-day warm-up ramp
- **Residential proxy**: SOCKS5 via SSH tunnel, Brazil geo-located

### Telegram Bridge

```bash
python telegram_bridge.py
# /start - Info
# /status - Server/VM health check
# Any text → forwarded to Claude CLI → response back
```

---

## Project Structure

```
hermes-cloud-studio/
├── server.py                    # PC: FastAPI backend (44 endpoints, WS, auth)
├── hermes_api_v2.py             # VM: API bridge (:8420)
├── hermes_desktop.py            # Legacy: PyInstaller desktop (deprecated)
├── telegram_bridge.py           # Telegram ↔ Claude CLI bridge
├── socks5_proxy.py              # Authenticated SOCKS5 proxy
├── gosom_scraper.py             # Docker-based Google Maps scraper
├── night_scraper.py             # Google Places API scraper
├── cloudflared.yml              # Cloudflare tunnel config
├── Hermes.bat                   # Quick launcher (finds .exe)
│
├── app/                         # Tauri 2.0 desktop app
│   ├── package.json             # @tauri-apps/cli v2
│   ├── src/                     # Minimal frontend assets
│   └── src-tauri/
│       ├── Cargo.toml           # Rust deps (tauri, tokio, serde)
│       ├── tauri.conf.json      # Window config, always loads from disk
│       ├── icons/               # App icons (PNG, ICO, ICNS)
│       └── src/
│           ├── main.rs          # Entry point
│           └── lib.rs           # Core: health loop, process mgmt, tray
│
├── dashboard/                   # Modular frontend
│   ├── index.html               # 10-page SPA (nav, pages, modals)
│   ├── styles.css               # Design tokens, components, animations
│   └── app.js                   # All logic (navigate, API, WebSocket)
│
├── linkedin/                    # Anti-detection automation
│   ├── config.py                # Rate limits, proxy, warm-up config
│   ├── viewer.py                # Profile visitor + data extraction
│   ├── stealth.py               # 11 JS anti-detection patches
│   ├── human.py                 # Mouse, typing, scroll simulation
│   ├── limiter.py               # Rate limiter with SQLite persistence
│   └── requirements.txt         # patchright, playwright-stealth
│
├── skills/                      # Hermes Agent skill definitions
│   ├── linkedin-post-generator.yaml
│   ├── linkedin-profile-researcher.yaml
│   ├── linkedin-connection-sender.yaml
│   ├── linkedin-engagement.yaml
│   ├── linkedin-trend-monitor.yaml
│   └── weekly-mission-planner.yaml
│
├── scripts/                     # Automation scripts
│   ├── pipeline.py              # Master orchestrator
│   ├── web_audit.py             # Website audit engine
│   └── outreach_generator.py    # Category-based message generation
│
└── docs/                        # Documentation
    └── HERMES-PROJECT-CONTEXT.md
```

---

## Quick Start

### Prerequisites

- Python 3.11+
- Rust 1.70+ (for Tauri build)
- Node.js 18+ (for Tauri CLI)
- Windows 10/11
- SSH key configured for VM access

### Installation

```bash
git clone https://github.com/caiolea0/hermes-cloud-studio.git
cd hermes-cloud-studio

# Python deps
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your credentials (VM_HOST, tokens, etc.)
```

### Running

```bash
# Option 1: Dashboard server only
python server.py
# → http://localhost:8500

# Option 2: Tauri desktop app (recommended)
Hermes.bat
# → Launches all services invisibly, opens dashboard window

# Option 3: Build Tauri from source
cd app && npm run tauri build
# → app/src-tauri/target/release/hermes.exe
```

### Development

```bash
# Dev mode (hot reload via server.py serving from disk)
cd app && npm run tauri dev

# The frontend always loads from http://localhost:8500
# Edit dashboard/*.js|*.css|*.html → refresh to see changes
```

---

## API Reference

### Dashboard Server (PC :8500)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/prospects` | List prospects (filterable) |
| POST | `/api/prospects` | Create prospect |
| PATCH | `/api/prospects/:id` | Update prospect |
| DELETE | `/api/prospects/:id` | Delete prospect |
| GET | `/api/prospects/stats` | Aggregated statistics |
| POST | `/api/audit/start` | Start batch audit |
| GET | `/api/audit/status` | Audit progress |
| GET | `/api/pipelines` | List pipeline templates |
| POST | `/api/pipelines` | Create pipeline (with schedule) |
| POST | `/api/pipelines/:id/execute` | Execute pipeline |
| GET | `/api/hermes/skills` | List agent skills |
| PATCH | `/api/hermes/skills/:name` | Toggle skill active state |
| GET | `/api/hermes/memory` | Get memory items |
| POST | `/api/hermes/memory` | Create memory item |
| DELETE | `/api/hermes/memory/:id` | Delete memory item |
| GET | `/api/hermes/status` | System health check |
| POST | `/api/claude/execute` | Execute AI command |
| WS | `/ws` | Real-time event stream |

### VM API (:8420)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/prospects` | All prospects (paginated) |
| GET | `/api/activities` | Activity log |
| GET | `/api/dashboard` | Dashboard stats |
| POST | `/api/scraper/start` | Start discovery scraper |
| POST | `/api/scraper/stop` | Stop scraper |
| GET | `/api/scraper/status` | Scraper state + logs |
| POST | `/api/audit/start` | Trigger audit batch |
| GET | `/api/hermes/skills` | List skills from YAML |
| PATCH | `/api/hermes/skills/:name` | Toggle skill |

---

## Configuration

### Environment Variables (.env)

```env
# VM Connection
VM_HOST=136.115.74.69
VM_USER=hermes-gcp
HERMES_VM_API=http://136.115.74.69:8420

# Authentication
HERMES_TOKEN=your-secret-token

# Services
AGENT_ZERO_URL=http://136.115.74.69:50080
AGENTMEMORY_URL=http://localhost:3111

# Telegram (optional)
TELEGRAM_BOT_TOKEN=your-bot-token
TELEGRAM_CHAT_ID=your-chat-id
```

### LinkedIn Config (linkedin/config.py)

```python
@dataclass
class LinkedInConfig:
    daily_profile_views: int = 70        # free account safe limit
    daily_connection_requests: int = 30
    warmup_days: int = 14                # gradual ramp-up period
    min_action_delay: float = 3.0        # seconds between actions
    page_dwell_max: float = 45.0         # max time on profile
    timezone: str = "America/Cuiaba"
    locale: str = "pt-BR"
```

---

## Security Notes

- Auth token required on all `/api/*` endpoints
- LinkedIn automation uses residential proxy + stealth patches
- Rate limiting prevents account bans (conservative defaults)
- Warm-up system ramps gradually over 14 days
- No credentials stored in repo (all via .env)
- Desktop app kills all processes on exit (no orphan processes)

---

## Commit History

| Commit | Description |
|--------|-------------|
| `feat(tauri)` | Desktop app with health loop, auto-restart, tray |
| `feat(dashboard)` | Skills, Memory, Missions panels + WebSocket + Claude markdown |
| `feat(skills)` | 6 LinkedIn AI skill YAML definitions |
| `feat(integrations)` | Telegram bridge + Cloudflare tunnel |
| `feat(auth)` | Token-based authentication |
| `refactor(dashboard)` | Modularized from 278KB monolith to CSS/JS/HTML |
| `feat(vm-api)` | Audit, outreach, pipeline, skills endpoints |

---

## License

Private repository. All rights reserved.

---

<p align="center">
  <sub>Built with FastAPI, Tauri, and a lot of automation by <a href="https://github.com/caiolea0">@caiolea0</a></sub>
</p>
