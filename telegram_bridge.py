"""Telegram ↔ Claude Code Bridge for mobile access to Hermes Command Center."""
import asyncio
import os
import logging
from pathlib import Path

from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes

logging.basicConfig(level=logging.INFO, format="%(asctime)s [TelegramBridge] %(message)s")
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ALLOWED_CHAT_ID = int(os.environ.get("TELEGRAM_CHAT_ID", "0"))
PROJECT_DIR = Path(__file__).parent
TIMEOUT = 120  # seconds max per command


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Forward user message to Claude CLI and return response."""
    if update.effective_chat.id != ALLOWED_CHAT_ID:
        logger.warning("Unauthorized chat_id: %s", update.effective_chat.id)
        return

    msg = update.message.text
    if not msg:
        return

    logger.info("Received: %s", msg[:80])
    await update.message.reply_text("⏳ Processando...", parse_mode=None)

    try:
        proc = await asyncio.create_subprocess_exec(
            "claude", "-p", msg,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(PROJECT_DIR)
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=TIMEOUT)
        response = stdout.decode("utf-8", errors="replace").strip()

        if not response and stderr:
            response = f"[stderr] {stderr.decode('utf-8', errors='replace')[:2000]}"
        if not response:
            response = "Sem resposta do Claude."

        # Telegram max message = 4096 chars
        for i in range(0, len(response), 4000):
            chunk = response[i:i+4000]
            await update.message.reply_text(chunk, parse_mode=None)

    except asyncio.TimeoutError:
        await update.message.reply_text("⏰ Timeout (>120s). Comando muito longo.", parse_mode=None)
    except FileNotFoundError:
        await update.message.reply_text("❌ Claude CLI nao encontrado. Verifique instalacao.", parse_mode=None)
    except Exception as e:
        logger.error("Error: %s", e)
        await update.message.reply_text(f"❌ Erro: {str(e)[:500]}", parse_mode=None)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    if update.effective_chat.id != ALLOWED_CHAT_ID:
        await update.message.reply_text("Nao autorizado.")
        return
    await update.message.reply_text(
        "🤖 Hermes Telegram Bridge ativo!\n\n"
        "Envie qualquer mensagem e ela sera processada pelo Claude Code.\n"
        "Contexto: projeto hermes-cloud-studio",
        parse_mode=None
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /status command — check if services are running."""
    if update.effective_chat.id != ALLOWED_CHAT_ID:
        return
    import httpx
    server_url = os.environ.get("HERMES_SERVER_URL", "http://localhost:8500")
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{server_url}/api/hermes/status")
            if r.status_code == 200:
                data = r.json()
                await update.message.reply_text(
                    f"✅ Server: online\n"
                    f"🖥️ VM: {'online' if data.get('vm_online') else 'offline'}\n"
                    f"📊 Prospects: {data.get('total_prospects', '?')}\n"
                    f"🔄 Last sync: {data.get('last_sync', '?')}",
                    parse_mode=None
                )
            else:
                await update.message.reply_text(f"⚠️ Server respondeu {r.status_code}", parse_mode=None)
    except Exception as e:
        await update.message.reply_text(f"❌ Server offline: {e}", parse_mode=None)


def main():
    if not TELEGRAM_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set!")
        return
    if not ALLOWED_CHAT_ID:
        logger.error("TELEGRAM_CHAT_ID not set!")
        return

    logger.info("Starting Telegram bridge (chat_id=%s)", ALLOWED_CHAT_ID)
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()


if __name__ == "__main__":
    main()
