"""Jobs proactivos con APScheduler (todos en Europe/Madrid).

QUÉ: cuatro jobs cron que usan la MISMA capa de datos que el agente y te
escriben por Telegram sin que preguntes nada:
  - 08:00 diario   → brief matutino (redactado por el agente)
  - 12:00 diario   → tareas envejecidas: >3 días sin tocar
  - 16:00 diario   → deadlines a ≤48h o ya vencidos (texto plano a propósito:
                      debe llegar aunque la API de Anthropic esté caída)
  - domingo 20:00  → retrospectiva semanal (redactada por el agente)

POR QUÉ AsyncIOScheduler: se engancha al mismo event loop que
python-telegram-bot, así los jobs usan app.bot.send_message directamente.
Las llamadas al agente (síncronas) se sacan a un hilo con asyncio.to_thread,
igual que en bot.py.
"""

import asyncio
import json
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram.ext import Application

from . import agente, config, db

log = logging.getLogger(__name__)

LIMITE_TELEGRAM = 4096


async def _enviar(app: Application, texto: str) -> None:
    for i in range(0, len(texto), LIMITE_TELEGRAM):
        await app.bot.send_message(chat_id=config.TELEGRAM_USER_ID,
                                   text=texto[i : i + LIMITE_TELEGRAM])


def _linea(t: dict) -> str:
    extra = f" · deadline {t['deadline']}" if t.get("deadline") else ""
    return f"• [{t['id']}] {t['titulo']} ({t['prioridad']}, {t['estado']}{extra})"


async def brief_matutino(app: Application) -> None:
    """Los datos los saca el código (fiable); el agente solo los redacta."""
    datos = {
        "tareas_activas": db.listar_tareas(),
        "deadlines_proximos_7_dias": db.listar_deadlines(7),
        "diario_de_ayer": db.diario_de(db.ayer()),
    }
    prompt = (
        "Redacta mi brief matutino para Telegram a partir de estos datos. "
        "Corto, priorizado y accionable. No llames a ninguna tool.\n\n"
        + json.dumps(datos, ensure_ascii=False, default=str)
    )
    try:
        texto = await asyncio.to_thread(agente.generar, prompt)
    except Exception:
        # Si la API falla, el brief llega igual: versión sin redactar
        log.exception("El agente falló generando el brief; mando la versión simple")
        lineas = [_linea(t) for t in datos["tareas_activas"]] or ["(sin tareas activas)"]
        texto = "Tareas activas:\n" + "\n".join(lineas)
    await _enviar(app, "☀️ Brief matutino\n\n" + texto)


async def aviso_deadlines(app: Application) -> None:
    proximas = db.listar_deadlines(2)
    if not proximas:
        return  # sin urgencias, sin ruido
    await _enviar(app, "⏰ Deadlines a menos de 48h (o vencidos):\n"
                  + "\n".join(_linea(t) for t in proximas))


async def envejecimiento(app: Application) -> None:
    viejas = db.tareas_envejecidas(3)
    if not viejas:
        return
    await _enviar(app, "🕸️ Tareas sin tocar desde hace más de 3 días — muévelas o mátalas:\n"
                  + "\n".join(_linea(t) for t in viejas))


async def retro_semanal(app: Application) -> None:
    datos = db.resumen_semana()
    prompt = (
        "Redacta mi retrospectiva semanal a partir de estos datos: qué se completó, "
        "qué se atascó y por qué, patrones que veas en diario y decisiones, y 2-3 "
        "propuestas concretas para la semana que viene. No llames a ninguna tool.\n\n"
        + json.dumps(datos, ensure_ascii=False, default=str)
    )
    try:
        texto = await asyncio.to_thread(agente.generar, prompt)
    except Exception:
        log.exception("El agente falló en la retro; mando los datos en bruto")
        texto = json.dumps(datos, ensure_ascii=False, indent=2, default=str)
    await _enviar(app, "📊 Retro semanal\n\n" + texto)


def crear_scheduler(app: Application) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=config.TZ)
    scheduler.add_job(brief_matutino, CronTrigger(hour=8, minute=0, timezone=config.TZ),
                      args=[app], id="brief_matutino")
    scheduler.add_job(envejecimiento, CronTrigger(hour=12, minute=0, timezone=config.TZ),
                      args=[app], id="envejecimiento")
    scheduler.add_job(aviso_deadlines, CronTrigger(hour=16, minute=0, timezone=config.TZ),
                      args=[app], id="aviso_deadlines")
    scheduler.add_job(retro_semanal, CronTrigger(day_of_week="sun", hour=20, minute=0, timezone=config.TZ),
                      args=[app], id="retro_semanal")
    return scheduler
