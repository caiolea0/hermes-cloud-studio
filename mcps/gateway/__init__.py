"""Hermes ContextForge Gateway — F.5.1 scaffold.

FastMCP 3.0 multiplex+auth+audit layer in front of 3 custom MCPs
(hermes-linkedin, hermes-prospects, hermes-skills — F.5.2 entrega).

Loopback-only bind 127.0.0.1:55401 on VM. Never exposed public.
PC dashboard consumes via SSH reverse tunnel (F.5.3).
"""
from .server import build_app, GATEWAY_VERSION

__all__ = ["build_app", "GATEWAY_VERSION"]
