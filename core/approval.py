"""
Approval: bot de Telegram para aprobación de publicaciones.
Flujo:
  1. Envía preview (imagen + caption) con botones ✅ Publicar / ❌ Regenerar
  2. Si ✅ → publica inmediatamente
  3. Si ❌ → regenera (máx MAX_REGENERATIONS veces), vuelve a enviar preview
  4. Sin respuesta en APPROVAL_WINDOW_HOURS → publica automáticamente
  5. Si agota regeneraciones → notifica y descarta el día
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    ContextTypes,
)

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

logger = logging.getLogger("approval")

STATE_FILE = BASE_DIR / "state" / "weekly_plan.json"

# Tokens de callback para los botones inline
CB_PUBLICAR = "publicar"
CB_REGENERAR = "regenerar"


def _cargar_plan() -> dict:
    with open(STATE_FILE, encoding="utf-8") as f:
        return json.load(f)


def _guardar_plan(plan: dict) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)


def _teclado_aprobacion(fecha: str) -> InlineKeyboardMarkup:
    """Genera los botones inline de aprobación."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Publicar", callback_data=f"{CB_PUBLICAR}:{fecha}"),
            InlineKeyboardButton("❌ Regenerar", callback_data=f"{CB_REGENERAR}:{fecha}"),
        ]
    ])


async def _enviar_preview_async(
    bot_token: str,
    chat_id: str,
    dia: dict,
) -> int:
    """Envía la preview de la story a Telegram y devuelve el message_id."""
    from telegram import Bot

    bot = Bot(token=bot_token)
    fecha = dia["fecha"]
    nombre_dia = dia["dia_semana"].upper()
    caption_texto = dia.get("caption", "Sin caption")
    hashtags = " ".join(dia.get("hashtags", []))
    story_path = Path(dia.get("story_path", ""))

    texto = (
        f"📸 *Preview del post — {nombre_dia} {fecha}*\n\n"
        f"{caption_texto}\n\n"
        f"_{hashtags}_\n\n"
        f"Tienes {os.getenv('APPROVAL_WINDOW_HOURS', 2)}h para responder.\n"
        f"Sin respuesta → publica automáticamente."
    )

    if story_path.exists():
        with open(story_path, "rb") as f:
            msg = await bot.send_photo(
                chat_id=chat_id,
                photo=f,
                caption=texto,
                parse_mode="Markdown",
                reply_markup=_teclado_aprobacion(fecha),
            )
    else:
        # Sin imagen — enviar solo texto
        logger.warning(f"Story no encontrada: {story_path} — enviando solo texto")
        msg = await bot.send_message(
            chat_id=chat_id,
            text=texto,
            parse_mode="Markdown",
            reply_markup=_teclado_aprobacion(fecha),
        )

    logger.info(f"Preview enviada a Telegram para {nombre_dia} {fecha} (msg_id={msg.message_id})")
    return msg.message_id


def enviar_para_aprobacion(dia: dict) -> None:
    """
    Envía la preview a Telegram y espera respuesta (bloqueante).
    Publicación automática si no hay respuesta en APPROVAL_WINDOW_HOURS.
    """
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    ventana_horas = float(os.getenv("APPROVAL_WINDOW_HOURS", 2))
    max_regen = int(os.getenv("MAX_REGENERATIONS", 3))

    if not bot_token or not chat_id:
        logger.warning("TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID no configurados — saltando aprobación")
        return

    asyncio.run(_enviar_preview_async(bot_token, chat_id, dia))

    # Esperar respuesta con polling usando asyncio
    asyncio.run(_esperar_respuesta(bot_token, chat_id, dia, ventana_horas, max_regen))


async def _esperar_respuesta(
    bot_token: str,
    chat_id: str,
    dia: dict,
    ventana_horas: float,
    max_regen: int,
) -> None:
    """
    Escucha callbacks de Telegram durante la ventana de aprobación.
    Gestiona la lógica de publicar / regenerar / timeout.
    """
    from telegram import Bot

    from core.publisher import publicar_story

    bot = Bot(token=bot_token)
    fecha = dia["fecha"]
    deadline = datetime.now() + timedelta(hours=ventana_horas)

    logger.info(f"Esperando respuesta hasta {deadline.strftime('%H:%M')} para {fecha}")

    offset = None
    while datetime.now() < deadline:
        updates = await bot.get_updates(offset=offset, timeout=30, allowed_updates=["callback_query"])

        for update in updates:
            offset = update.update_id + 1
            if not update.callback_query:
                continue

            query = update.callback_query
            await query.answer()

            if not query.data or not (
                query.data.startswith(CB_PUBLICAR) or query.data.startswith(CB_REGENERAR)
            ):
                continue

            accion, fecha_cb = query.data.split(":", 1)
            if fecha_cb != fecha:
                continue  # callback de otro día

            plan = _cargar_plan()
            dia_actual = plan.get(fecha, dia)

            if accion == CB_PUBLICAR:
                logger.info(f"✅ Aprobado por el usuario: {fecha}")
                await query.edit_message_caption(
                    caption=f"✅ Publicando {dia_actual['dia_semana'].upper()} {fecha}...",
                )
                try:
                    publicar_story(dia_actual)
                    plan[fecha]["estado"] = "publicado"
                    _guardar_plan(plan)
                    await bot.send_message(chat_id=chat_id, text=f"✅ Publicado correctamente: {fecha}")
                except Exception as e:
                    logger.error(f"Error publicando {fecha}: {e}")
                    await bot.send_message(chat_id=chat_id, text=f"❌ Error al publicar {fecha}: {e}")
                return

            elif accion == CB_REGENERAR:
                intentos = dia_actual.get("intentos_regeneracion", 0) + 1
                plan[fecha]["intentos_regeneracion"] = intentos
                _guardar_plan(plan)

                if intentos >= max_regen:
                    logger.warning(f"Máximo de regeneraciones alcanzado para {fecha}")
                    plan[fecha]["estado"] = "descartado"
                    _guardar_plan(plan)
                    await query.edit_message_caption(
                        caption=f"⚠️ Descartado tras {max_regen} regeneraciones: {fecha}",
                    )
                    await bot.send_message(
                        chat_id=chat_id,
                        text=f"⚠️ El post del {dia_actual['dia_semana']} {fecha} ha sido descartado.",
                    )
                    return

                logger.info(f"❌ Regenerando {fecha} (intento {intentos}/{max_regen})")
                await query.edit_message_caption(
                    caption=f"🔄 Regenerando... (intento {intentos}/{max_regen})",
                )
                await _regenerar_y_reenviar(bot, chat_id, fecha, dia_actual, plan, ventana_horas, max_regen)
                return

        # Pequeña pausa para no saturar la API de Telegram
        await asyncio.sleep(5)

    # Timeout: publicar automáticamente
    logger.info(f"Timeout alcanzado para {fecha} — publicando automáticamente")
    plan = _cargar_plan()
    dia_actual = plan.get(fecha, dia)

    from core.publisher import publicar_story
    try:
        publicar_story(dia_actual)
        plan[fecha]["estado"] = "publicado"
        _guardar_plan(plan)
        await bot.send_message(
            chat_id=chat_id,
            text=f"⏱ Publicado automáticamente (sin respuesta en {ventana_horas}h): {fecha}",
        )
    except Exception as e:
        logger.error(f"Error en publicación automática {fecha}: {e}")
        await bot.send_message(chat_id=chat_id, text=f"❌ Error al publicar {fecha}: {e}")


async def _regenerar_y_reenviar(
    bot,
    chat_id: str,
    fecha: str,
    dia: dict,
    plan: dict,
    ventana_horas: float,
    max_regen: int,
) -> None:
    """Regenera caption e imagen y envía nuevo preview."""
    from agents.compositor import montar_story
    from agents.copy_agent import generar_caption
    from agents.image_agent import generar_imagen

    modelo_ollama = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
    modelo_sdxl = os.getenv("SDXL_MODEL", "stabilityai/sdxl-turbo")

    try:
        # Borrar imagen anterior para forzar regeneración
        if dia.get("image_path"):
            old_img = Path(dia["image_path"])
            if old_img.exists():
                old_img.unlink()
        if dia.get("story_path"):
            old_story = Path(dia["story_path"])
            if old_story.exists():
                old_story.unlink()

        resultado_copy = generar_caption(dia, modelo=modelo_ollama)
        dia["caption"] = resultado_copy["caption"]
        dia["hashtags"] = resultado_copy["hashtags"]

        image_path = generar_imagen(dia, modelo=modelo_sdxl)
        dia["image_path"] = str(image_path)

        story_path = montar_story(
            image_path=image_path,
            caption=dia["caption"],
            hashtags=dia.get("hashtags", []),
            fecha=fecha,
            dia_semana=dia["dia_semana"],
        )
        dia["story_path"] = str(story_path)
        plan[fecha] = dia
        _guardar_plan(plan)

        await _enviar_preview_async(
            bot._token, chat_id, dia
        )
        await _esperar_respuesta(bot._token, chat_id, dia, ventana_horas, max_regen)

    except Exception as e:
        logger.error(f"Error en regeneración de {fecha}: {e}")
        await bot.send_message(
            chat_id=chat_id,
            text=f"❌ Error al regenerar el post del {dia['dia_semana']}: {e}",
        )


if __name__ == "__main__":
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        level=logging.INFO,
    )

    # Test de imports y configuración — no envía nada sin token real
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")

    print("── Test de configuración approval.py ──")
    print(f"TELEGRAM_BOT_TOKEN: {'configurado' if bot_token else 'NO configurado'}")
    print(f"TELEGRAM_CHAT_ID  : {'configurado' if chat_id else 'NO configurado'}")
    print(f"APPROVAL_WINDOW_HOURS: {os.getenv('APPROVAL_WINDOW_HOURS', 2)}")
    print(f"MAX_REGENERATIONS    : {os.getenv('MAX_REGENERATIONS', 3)}")

    if not bot_token:
        print("\n⚠ Sin TELEGRAM_BOT_TOKEN en .env — módulo listo pero no puede conectar")
        print("  Configura el .env con las credenciales para probar el envío real")
    else:
        print("\nTodos los parámetros configurados — módulo listo")
