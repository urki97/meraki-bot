"""Punto de entrada: valida configuración, crea la BD y arranca bot + scheduler.

Se ejecuta como módulo (python -m src.main) para que funcionen los imports
relativos del paquete.
"""

import logging
import os

from telegram.ext import Application

from . import bot, config, db, scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)  # silencia el eco de cada request

log = logging.getLogger(__name__)


def _comprobar_config() -> None:
    """Falla pronto y con mensajes claros, no a la primera petición."""
    errores = []
    if not config.TELEGRAM_BOT_TOKEN:
        errores.append("TELEGRAM_BOT_TOKEN vacío (créalo con @BotFather)")
    if not os.getenv("ANTHROPIC_API_KEY"):
        errores.append("ANTHROPIC_API_KEY vacío (console.anthropic.com)")
    for e in errores:
        log.error("CONFIG: %s", e)
    if errores:
        raise SystemExit("Faltan credenciales en el .env — ver errores de arriba")
    if not config.TELEGRAM_USER_ID:
        # No es fatal: el bot arranca y /start te dice tu ID para el .env
        log.warning("TELEGRAM_USER_ID vacío: el bot ignorará todos los mensajes. "
                    "Mándale /start para ver tu ID y ponlo en el .env.")


async def _post_init(app: Application) -> None:
    """PTB llama a esto con el event loop ya corriendo: el sitio correcto
    para arrancar el AsyncIOScheduler (necesita un loop activo)."""
    sch = scheduler.crear_scheduler(app)
    sch.start()
    for job in sch.get_jobs():
        log.info("Job '%s' → próxima ejecución: %s", job.id, job.next_run_time)


def main() -> None:
    _comprobar_config()
    db.init_db()
    log.info("BD lista en %s", config.DB_PATH)

    app = (
        Application.builder()
        .token(config.TELEGRAM_BOT_TOKEN)
        .post_init(_post_init)
        .build()
    )
    bot.registrar_handlers(app)

    log.info("Arrancando bot (long polling) — modelo=%s effort=%s tz=%s",
             config.MODEL_ID, config.EFFORT, config.TZ)
    app.run_polling(allowed_updates=["message"])


if __name__ == "__main__":
    main()
