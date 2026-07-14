"""
Config check: valida la configuración antes de arrancar el bot.

Distingue dos niveles:
  - errores: impiden publicar en producción (DRY_RUN=false) — el pipeline aborta
  - avisos:  funcionalidad degradada pero el bot puede seguir (p.ej. sin Telegram)

En DRY_RUN=true casi todo son avisos, porque no se llama a ninguna API real.
"""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

logger = logging.getLogger("config_check")


def _flag(nombre: str, por_defecto: str = "false") -> bool:
    return os.getenv(nombre, por_defecto).lower() in ("true", "1", "yes")


def comprobar_env() -> tuple[list[str], list[str]]:
    """Comprueba las variables de entorno. Devuelve (errores, avisos)."""
    errores: list[str] = []
    avisos: list[str] = []
    dry_run = _flag("DRY_RUN", "true")

    # Telegram — sin él no hay aprobación, pero el bot puede publicar solo
    if not os.getenv("TELEGRAM_BOT_TOKEN") or not os.getenv("TELEGRAM_CHAT_ID"):
        avisos.append("Telegram sin configurar — no habrá previews de aprobación")

    # Credenciales por red — solo son error si la red está activa y no es DRY_RUN
    if _flag("PUBLISH_INSTAGRAM", "true"):
        if not os.getenv("IG_USER_ID") or not os.getenv("IG_ACCESS_TOKEN"):
            (avisos if dry_run else errores).append(
                "Instagram activo pero faltan IG_USER_ID / IG_ACCESS_TOKEN"
            )

    if _flag("PUBLISH_FACEBOOK", "true"):
        if not os.getenv("FACEBOOK_PAGE_ID") or not os.getenv("IG_ACCESS_TOKEN"):
            (avisos if dry_run else errores).append(
                "Facebook activo pero faltan FACEBOOK_PAGE_ID / IG_ACCESS_TOKEN"
            )

    if _flag("PUBLISH_TWITTER", "false"):
        claves_tw = ["TWITTER_API_KEY", "TWITTER_API_SECRET",
                     "TWITTER_ACCESS_TOKEN", "TWITTER_ACCESS_SECRET"]
        if not all(os.getenv(k) for k in claves_tw):
            (avisos if dry_run else errores).append(
                "Twitter activo pero faltan credenciales TWITTER_*"
            )

    # Cloudinary — necesario para IG/FB en producción (Meta exige URL pública)
    redes_meta = _flag("PUBLISH_INSTAGRAM", "true") or _flag("PUBLISH_FACEBOOK", "true")
    claves_cld = ["CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET"]
    if redes_meta and not all(os.getenv(k) for k in claves_cld):
        (avisos if dry_run else errores).append(
            "Faltan credenciales de Cloudinary — IG/FB necesitan URL pública de imagen"
        )

    return errores, avisos


def comprobar_ficheros() -> tuple[list[str], list[str]]:
    """Comprueba que existen los ficheros que el pipeline necesita."""
    errores: list[str] = []
    avisos: list[str] = []

    imprescindibles = [
        BASE_DIR / "config" / "pautas.yaml",
        BASE_DIR / "config" / "calendar.yaml",
    ]
    for ruta in imprescindibles:
        if not ruta.exists():
            errores.append(f"Falta fichero de configuración: {ruta.relative_to(BASE_DIR)}")

    if not (BASE_DIR / "assets" / "logo.png").exists():
        avisos.append("Falta assets/logo.png — las stories saldrán sin logo")

    if not (BASE_DIR / "assets" / "fonts" / "Poppins-Bold.ttf").exists():
        avisos.append("Falta Poppins-Bold.ttf — se usará una fuente del sistema")

    return errores, avisos


def comprobar_ollama() -> list[str]:
    """Comprueba que Ollama responde y tiene el modelo configurado. Solo avisos."""
    avisos: list[str] = []
    modelo = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
    try:
        import ollama
        respuesta = ollama.list()
        modelos = [m.get("name", m.get("model", "")) for m in respuesta.get("models", [])]
        if not any(modelo in m for m in modelos):
            avisos.append(f"Ollama responde pero no tiene el modelo {modelo} — hacer 'ollama pull {modelo}'")
    except Exception as e:
        avisos.append(f"Ollama no responde ({e}) — los captions usarán el enfoque por defecto")
    return avisos


def comprobar_todo(con_ollama: bool = True) -> dict:
    """
    Ejecuta todas las comprobaciones.
    Devuelve {"errores": [...], "avisos": [...], "ok": bool}.
    ok=False solo si hay errores (los avisos no bloquean).
    """
    errores_env, avisos_env = comprobar_env()
    errores_fich, avisos_fich = comprobar_ficheros()
    avisos_ollama = comprobar_ollama() if con_ollama else []

    errores = errores_env + errores_fich
    avisos = avisos_env + avisos_fich + avisos_ollama

    for e in errores:
        logger.error(f"CONFIG: {e}")
    for a in avisos:
        logger.warning(f"CONFIG: {a}")

    return {"errores": errores, "avisos": avisos, "ok": not errores}


if __name__ == "__main__":
    import sys

    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        level=logging.INFO,
    )

    print("\n── Comprobación de configuración ──────────────────────────")
    print(f"DRY_RUN: {os.getenv('DRY_RUN', 'true')}\n")

    resultado = comprobar_todo()

    if resultado["errores"]:
        print("ERRORES (bloquean la publicación):")
        for e in resultado["errores"]:
            print(f"  ✗ {e}")
    if resultado["avisos"]:
        print("\nAvisos:")
        for a in resultado["avisos"]:
            print(f"  ⚠ {a}")
    if resultado["ok"] and not resultado["avisos"]:
        print("Todo correcto ✓")
    elif resultado["ok"]:
        print("\nConfiguración válida (con avisos) ✓")

    sys.exit(0 if resultado["ok"] else 1)
