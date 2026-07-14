"""
Comandos: bot de Telegram para controlar el pipeline desde el móvil.

Comandos disponibles:
  /estado          — resumen del plan semanal y últimas publicaciones
  /generar         — lanza el pipeline completo ahora (como --ahora)
  /preview <dia>   — genera el preview de un día (miercoles/jueves/viernes)
  /ayuda           — lista de comandos

Solo responde al TELEGRAM_CHAT_ID configurado — cualquier otro chat se ignora.
Se ejecuta como proceso aparte del scheduler:
    python core/comandos.py
"""

import json
import logging
import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

logger = logging.getLogger("comandos")

STATE_FILE = BASE_DIR / "state" / "weekly_plan.json"

# Emojis por estado del plan para el resumen de /estado
EMOJI_ESTADO = {
    "pendiente": "⏳",
    "pendiente_aprobacion": "📸",
    "publicado": "✅",
    "descartado": "🗑",
    "no_publicar": "➖",
    "error": "❌",
}


def _autorizado(update: Update) -> bool:
    """Solo responde al chat configurado en .env."""
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    return chat_id and str(update.effective_chat.id) == str(chat_id)


async def cmd_estado(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Resumen del plan semanal y últimas publicaciones del historial."""
    if not _autorizado(update):
        return

    lineas = ["📋 *Plan de la semana*\n"]
    if STATE_FILE.exists():
        with open(STATE_FILE, encoding="utf-8") as f:
            plan = json.load(f)
        for fecha, dia in sorted(plan.items()):
            emoji = EMOJI_ESTADO.get(dia.get("estado", "?"), "❓")
            nombre = dia.get("dia_semana", "?")
            detalle = dia.get("tema") or dia.get("motivo", "")
            lineas.append(f"{emoji} {nombre} {fecha} — {detalle}")
    else:
        lineas.append("_No hay plan generado aún. Usa /generar._")

    # Últimas publicaciones del historial
    try:
        from core.historial import ultimas
        historial = ultimas(3)
        if historial:
            lineas.append("\n📜 *Últimas publicaciones*")
            for e in historial:
                redes = ", ".join(e.get("redes", []))
                lineas.append(f"• {e['fecha']} ({redes}): _{e['caption'][:50]}…_")
    except Exception:
        pass

    await update.message.reply_text("\n".join(lineas), parse_mode="Markdown")


async def cmd_generar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lanza el pipeline semanal completo en un proceso aparte."""
    if not _autorizado(update):
        return

    subprocess.Popen(
        [sys.executable, str(BASE_DIR / "core" / "scheduler.py"), "--ahora"],
        cwd=BASE_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    await update.message.reply_text(
        "🚀 Pipeline lanzado. Los previews irán llegando según se generen "
        "(cada imagen tarda 1-2 min)."
    )


async def cmd_preview(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Genera el preview de un día concreto: /preview jueves"""
    if not _autorizado(update):
        return

    dias_validos = ("miercoles", "jueves", "viernes")
    dia = context.args[0].lower() if context.args else ""
    if dia not in dias_validos:
        await update.message.reply_text(
            f"Uso: /preview <dia>\nDías disponibles: {', '.join(dias_validos)}"
        )
        return

    subprocess.Popen(
        [sys.executable, str(BASE_DIR / "generar_preview.py"), dia],
        cwd=BASE_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    await update.message.reply_text(f"🎨 Generando preview del {dia}… (1-2 min)")


async def cmd_ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lista de comandos disponibles."""
    if not _autorizado(update):
        return

    await update.message.reply_text(
        "🤖 *Meraki Bot — comandos*\n\n"
        "/estado — plan de la semana y últimas publicaciones\n"
        "/generar — lanzar el pipeline completo ahora\n"
        "/preview <dia> — preview de miercoles/jueves/viernes\n"
        "/ayuda — este mensaje",
        parse_mode="Markdown",
    )


def iniciar_bot_comandos() -> None:
    """Arranca el bot de comandos en modo polling (bloqueante)."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN no configurado — no se puede arrancar")
        sys.exit(1)

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("estado", cmd_estado))
    app.add_handler(CommandHandler("generar", cmd_generar))
    app.add_handler(CommandHandler("preview", cmd_preview))
    app.add_handler(CommandHandler(["ayuda", "start", "help"], cmd_ayuda))

    logger.info("Bot de comandos iniciado — esperando mensajes")
    app.run_polling(allowed_updates=["message"])


if __name__ == "__main__":
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        level=logging.INFO,
    )
    iniciar_bot_comandos()
