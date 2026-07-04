"""Capa Telegram: handlers de comandos, texto y notas de voz.

QUÉ: recibe los updates, filtra que seas TÚ (allowlist por user id), delega
en voz.py (transcripción) y agente.py (respuesta) y contesta troceando a los
4096 caracteres que permite un mensaje de Telegram.
POR QUÉ asyncio.to_thread: el SDK de Anthropic y Whisper son síncronos; si
se llamaran directamente bloquearían el event loop del bot entero (no
podrías ni mandar otro mensaje mientras piensa). to_thread los saca a un
hilo y el bot sigue respondiendo.
"""

import asyncio
import logging
import os
import tempfile

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from . import agente, config, memoria
from . import voz as voz_mod

log = logging.getLogger(__name__)

LIMITE_TELEGRAM = 4096


def registrar_handlers(app: Application) -> None:
    solo_yo = filters.User(user_id=config.TELEGRAM_USER_ID)
    # /start SIN filtro a propósito: a un desconocido le dice "no" y a ti,
    # la primera vez, te enseña tu ID numérico para ponerlo en el .env
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("reset", cmd_reset, filters=solo_yo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & solo_yo, manejar_texto))
    app.add_handler(MessageHandler(filters.VOICE & solo_yo, manejar_voz))


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    usuario = update.effective_user
    if usuario is None or usuario.id != config.TELEGRAM_USER_ID:
        uid = usuario.id if usuario else "?"
        await update.message.reply_text(
            f"No autorizado. Tu ID de Telegram es: {uid} "
            "(si eres el dueño, ponlo en TELEGRAM_USER_ID del .env y reinicia)."
        )
        return
    await update.message.reply_text(
        "👋 Asesor operativo. Mándame texto o una nota de voz.\n"
        "/reset borra el hilo de conversación (tareas y diario no se tocan)."
    )


async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    memoria.reset(update.effective_chat.id)
    await update.message.reply_text("🧹 Conversación reiniciada. Los datos en SQLite siguen intactos.")


def _procesar(chat_id: int, texto: str) -> str:
    """Síncrono a propósito: se ejecuta dentro de asyncio.to_thread."""
    historial = memoria.obtener(chat_id)
    respuesta, nuevo_historial = agente.conversar(historial, texto)
    memoria.guardar(chat_id, nuevo_historial)
    return respuesta


async def _responder(update: Update, texto: str) -> None:
    for i in range(0, len(texto), LIMITE_TELEGRAM):
        await update.message.reply_text(texto[i : i + LIMITE_TELEGRAM])


async def manejar_texto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    await chat.send_action(ChatAction.TYPING)
    try:
        respuesta = await asyncio.to_thread(_procesar, chat.id, update.message.text)
    except Exception:
        log.exception("Error procesando mensaje de texto")
        await update.message.reply_text("💥 Algo falló hablando con el agente. Mira los logs del contenedor.")
        return
    await _responder(update, respuesta)


async def manejar_voz(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    await chat.send_action(ChatAction.TYPING)

    # 1) Descargar el .oga de Telegram a un temporal y transcribirlo
    try:
        fichero = await update.message.voice.get_file()
        with tempfile.TemporaryDirectory() as tmp:
            ruta = os.path.join(tmp, "nota.oga")
            await fichero.download_to_drive(ruta)
            texto = await asyncio.to_thread(voz_mod.transcribir, ruta)
    except Exception:
        log.exception("Error transcribiendo nota de voz")
        await update.message.reply_text("💥 No pude transcribir la nota de voz. Mira los logs (¿GPU/Whisper?).")
        return

    if not texto:
        await update.message.reply_text("🎙️ No he entendido nada en el audio.")
        return

    # 2) Eco de la transcripción (para que veas qué entendió) y respuesta
    await update.message.reply_text(f"🎙️ «{texto}»")
    await chat.send_action(ChatAction.TYPING)
    try:
        respuesta = await asyncio.to_thread(_procesar, chat.id, texto)
    except Exception:
        log.exception("Error procesando la transcripción")
        await update.message.reply_text("💥 Transcribí el audio pero falló el agente. Mira los logs.")
        return
    await _responder(update, respuesta)
