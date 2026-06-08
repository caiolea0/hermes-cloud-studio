"""Hermes LinkedIn Automation — Anti-Detection Automation Suite.

Modules:
    stealth         — Browser launch with full anti-detection (Patchright + fingerprint patches)
    human           — Human behavior simulation (Bezier mouse, typing cadence, scroll)
    viewer          — LinkedIn profile visiting with session management
    engager         — Post engagement: read posts, AI comment (Ollama), like
    connector       — Connection requests with optional AI-personalized notes
    company_finder  — Discover recruiters/HR at target companies
    limiter         — Rate limiting, warm-up tracking, daily/weekly caps
    config          — All constants and safety thresholds
"""
from .viewer import LinkedInViewer
from .engager import LinkedInEngager
from .connector import LinkedInConnector
from .company_finder import CompanyFinder
from .config import LinkedInConfig

__all__ = ["LinkedInViewer", "LinkedInEngager", "LinkedInConnector", "CompanyFinder", "LinkedInConfig"]
