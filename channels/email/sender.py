"""Email channel SMTP sender (MERGED-010 E.1).

Gmail App Password via smtplib + STARTTLS. Limiter-gated.
Multipart/alternative (text + html). Reply-To + custom headers (X-Hermes-*).
Retry com backoff exponencial em erros temporários (4xx/network).
"""
from __future__ import annotations

import logging
import smtplib
import ssl
import time
import uuid
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from typing import Optional

from .config import EmailConfig
from .limiter import EmailLimiter


logger = logging.getLogger("channels.email.sender")


class EmailSendError(RuntimeError):
    """Erro de envio que NÃO pôde ser resolvido por retry."""


class EmailRateLimited(RuntimeError):
    """Bloqueado pelo limiter (cap atingido OU fora do working hours)."""


# Erros temporários — retry com backoff.
_TRANSIENT_SMTP_CODES = {421, 450, 451, 452, 454}


class EmailSender:
    """Envio SMTP authenticated via Gmail App Password.

    Uso típico:
        sender = EmailSender.from_settings()
        sender.send(
            to="prospect@example.com",
            subject="Auditoria gratuita do seu Google Meu Negócio",
            text="Olá...",
            html="<p>Olá...</p>",
            campaign_id="lead-gen-01",
        )
    """

    def __init__(self, config: EmailConfig, limiter: Optional[EmailLimiter] = None):
        self.config = config
        self.limiter = limiter or EmailLimiter(config)
        self.config.assert_ready()

    @classmethod
    def from_settings(cls) -> "EmailSender":
        cfg = EmailConfig.from_settings()
        return cls(cfg)

    # ------- core -------

    def _build_message(
        self,
        to: str,
        subject: str,
        text: str,
        html: Optional[str],
        from_name: Optional[str],
        reply_to: Optional[str],
        headers: Optional[dict],
        campaign_id: Optional[str],
    ) -> tuple[EmailMessage, str]:
        msg = EmailMessage()
        sender_addr = (
            formataddr((from_name, self.config.from_address))
            if from_name
            else self.config.from_address
        )
        msg["From"] = sender_addr
        msg["To"] = to
        msg["Subject"] = subject
        message_id = make_msgid(domain="hermes.local")
        msg["Message-ID"] = message_id
        if reply_to or self.config.reply_to:
            msg["Reply-To"] = reply_to or self.config.reply_to
        if campaign_id:
            msg["X-Hermes-Campaign-Id"] = campaign_id
        msg["X-Hermes-Run-Id"] = uuid.uuid4().hex[:12]
        for k, v in (self.config.default_headers or {}).items():
            msg[k] = v
        for k, v in (headers or {}).items():
            msg[k] = v

        msg.set_content(text or "")
        if html:
            msg.add_alternative(html, subtype="html")
        return msg, message_id

    def _smtp_send(self, msg: EmailMessage) -> None:
        ctx = ssl.create_default_context()
        with smtplib.SMTP(
            self.config.smtp_host, self.config.smtp_port, timeout=self.config.timeout
        ) as s:
            s.ehlo()
            s.starttls(context=ctx)
            s.ehlo()
            s.login(self.config.from_address, self.config.app_password)
            s.send_message(msg)

    def send(
        self,
        to: str,
        subject: str,
        text: str = "",
        html: Optional[str] = None,
        from_name: Optional[str] = None,
        reply_to: Optional[str] = None,
        headers: Optional[dict] = None,
        campaign_id: Optional[str] = None,
        skip_limiter: bool = False,
    ) -> dict:
        """Envia email. Retorna {ok, message_id, status, reason}.

        Levanta EmailRateLimited se gate do limiter bloquear.
        Levanta EmailSendError se SMTP falhar após retries.
        """
        if not skip_limiter:
            ok, reason = self.limiter.can_send()
            if not ok:
                raise EmailRateLimited(reason or "rate_limited")

        msg, message_id = self._build_message(
            to=to,
            subject=subject,
            text=text,
            html=html,
            from_name=from_name,
            reply_to=reply_to,
            headers=headers,
            campaign_id=campaign_id,
        )

        last_err: Optional[Exception] = None
        for attempt in range(self.config.retry_max):
            try:
                self._smtp_send(msg)
                self.limiter.record_sent(
                    recipient=to, message_id=message_id, campaign_id=campaign_id
                )
                logger.info(
                    "email_sent recipient=%s campaign=%s msg_id=%s",
                    to,
                    campaign_id or "-",
                    message_id,
                )
                return {
                    "ok": True,
                    "message_id": message_id,
                    "status": "sent",
                    "attempt": attempt + 1,
                }
            except smtplib.SMTPResponseException as e:
                last_err = e
                if e.smtp_code in _TRANSIENT_SMTP_CODES and attempt + 1 < self.config.retry_max:
                    backoff = self.config.retry_backoff * (2 ** attempt)
                    logger.warning(
                        "email_transient code=%s attempt=%s backoff=%.1fs err=%s",
                        e.smtp_code,
                        attempt + 1,
                        backoff,
                        e.smtp_error,
                    )
                    time.sleep(backoff)
                    continue
                break
            except (smtplib.SMTPException, OSError) as e:
                last_err = e
                if attempt + 1 < self.config.retry_max:
                    backoff = self.config.retry_backoff * (2 ** attempt)
                    logger.warning(
                        "email_network attempt=%s backoff=%.1fs err=%s",
                        attempt + 1,
                        backoff,
                        e,
                    )
                    time.sleep(backoff)
                    continue
                break

        err_str = repr(last_err) if last_err else "unknown_error"
        self.limiter.record_failed(recipient=to, error=err_str, campaign_id=campaign_id)
        logger.error("email_failed recipient=%s campaign=%s err=%s", to, campaign_id or "-", err_str)
        raise EmailSendError(err_str)
