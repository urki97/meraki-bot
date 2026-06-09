# meraki-bot

Bot de publicaciones automáticas para **Meraki Bar & Cocktails** — Bilbao.

Genera las stories y posts de la semana, los manda al móvil para dar el OK, y los sube a Instagram, Facebook y Twitter.

---

## Qué hace

Cada lunes a las 9:00 el bot:

- Decide qué publicar cada día según la temática (mojitos los miércoles, pintxopote los jueves, tortillas los viernes, cócteles el sábado, vermú el domingo)
- Escribe el caption con IA local (Ollama)
- Genera la imagen con SDXL-Turbo
- Monta la story (1080×1920) y el feed (1080×1080)
- Manda un preview al Telegram del bar — se puede aprobar, rechazar o tocar qué redes usar
- Si en 2 horas no hay respuesta, publica solo

Lunes y martes el bar está cerrado, no publica nada. Miércoles, jueves y viernes rotan semanalmente para no saturar.

---

## Stack

| Qué | Para qué |
|-----|----------|
| Ollama / llama3.1:8b | Planificación y captions |
| SDXL-Turbo | Generación de imágenes |
| Pillow | Composición de stories y feeds |
| python-telegram-bot | Preview y aprobación |
| Meta Graph API | Instagram + Facebook |
| Tweepy | Twitter/X |
| APScheduler | Cron semanal |

Ollama y SDXL no caben en VRAM al mismo tiempo — el pipeline los usa en secuencia y libera memoria entre pasos.

---

## Requisitos

- Ubuntu / WSL2 con Python 3.14
- GPU NVIDIA con al menos 8 GB VRAM
- Ollama corriendo localmente con `llama3.1:8b`
- Token de bot de Telegram
- Credenciales Meta Graph API y Twitter/X (opcionales hasta producción)

---

## Instalación

```bash
git clone git@github.com:urki97/meraki-bot.git
cd meraki-bot

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# editar .env con los tokens
```

---

## Uso

```bash
source .venv/bin/activate

# Arranca el scheduler (cron lunes 9:00)
python core/scheduler.py

# Forzar ejecución ahora mismo
python core/scheduler.py --ahora

# Preview de un día concreto (usa imagen cacheada si existe)
python generar_preview.py miercoles
python generar_preview.py jueves
python generar_preview.py viernes

# Tests sin GPU ni credenciales
python -m pytest tests/ -v
```

---

## Variables de entorno

```env
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

IG_USER_ID=
IG_ACCESS_TOKEN=
FACEBOOK_PAGE_ID=

TWITTER_API_KEY=
TWITTER_API_SECRET=
TWITTER_ACCESS_TOKEN=
TWITTER_ACCESS_SECRET=
TWITTER_BEARER_TOKEN=

PUBLISH_INSTAGRAM=true
PUBLISH_FACEBOOK=true
PUBLISH_TWITTER=false

DRY_RUN=true
APPROVAL_WINDOW_HOURS=2
MAX_REGENERATIONS=3
```

---

## Pendiente para producción

- Credenciales Meta Graph API (las tiene el propietario del bar)
- CDN o bucket para alojar las imágenes antes de subirlas a Instagram
- Credenciales Twitter/X si se quiere activar (`PUBLISH_TWITTER=false` por defecto)
