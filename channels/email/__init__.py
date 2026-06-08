"""Email channel — SMTP sender, warmup ramp, rate limiter, tracking.

MERGED-010 (E.1). Pattern paralelo ao linkedin/.
"""
from .config import EmailConfig
from .limiter import EmailLimiter
from .sender import EmailSender, EmailSendError, EmailRateLimited

__all__ = [
    "EmailConfig",
    "EmailLimiter",
    "EmailSender",
    "EmailSendError",
    "EmailRateLimited",
]
