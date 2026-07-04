"""Configuración centralizada: todo sale de variables de entorno (.env).

POR QUÉ: el mismo código corre en Docker (docker compose pasa el .env con
env_file) y en local (python-dotenv carga el .env si existe). Ninguna clave
va hardcodeada ni al repo.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # en Docker no hace nada (las vars ya están); en local carga .env

BASE_DIR = Path(__file__).resolve().parent.parent

# --- Credenciales (ANTHROPIC_API_KEY la lee el SDK directamente del entorno)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_USER_ID = int(os.getenv("TELEGRAM_USER_ID", "0") or "0")

# --- Agente
MODEL_ID = os.getenv("MODEL_ID", "claude-fable-5")
# low|medium|high|xhigh|max — más effort = mejores respuestas pero más
# latencia y coste. Para un chat interactivo, medium es buen punto de partida.
EFFORT = os.getenv("EFFORT", "medium")
# Tope duro de tokens de salida POR LLAMADA. En fable-5 el thinking (siempre
# activo) también cuenta contra este límite, así que no conviene bajarlo mucho.
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "16000"))
# Máximo de vueltas del bucle agéntico por turno (corta bucles infinitos de tools)
MAX_ITERACIONES = int(os.getenv("MAX_ITERACIONES", "15"))
# Mensajes de conversación que se conservan en memoria por chat
MAX_HISTORIAL = int(os.getenv("MAX_HISTORIAL", "40"))

# --- Rutas y zona horaria
DB_PATH = os.getenv("DB_PATH", str(BASE_DIR / "data" / "asesor.db"))
PROMPT_PATH = os.getenv("PROMPT_PATH", str(BASE_DIR / "prompts" / "sistema.md"))
TZ = os.getenv("TZ", "Europe/Madrid")

# --- Whisper (transcripción de notas de voz)
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "large-v3")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cuda")      # "cpu" si no hay GPU
WHISPER_COMPUTE = os.getenv("WHISPER_COMPUTE", "float16")  # "int8" con cpu
WHISPER_IDIOMA = os.getenv("WHISPER_IDIOMA", "es")         # "" = autodetectar
