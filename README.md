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

# Bot de comandos de Telegram (proceso aparte)
python core/comandos.py

# Preview de un día concreto (usa imagen cacheada si existe)
python generar_preview.py miercoles
python generar_preview.py jueves
python generar_preview.py viernes

# Comprobar configuración
python core/config_check.py

# Tests sin GPU ni credenciales
python -m pytest tests/ -v
```

### Comandos de Telegram

Con `core/comandos.py` corriendo, desde el chat del bar:

- `/estado` — plan de la semana y últimas publicaciones
- `/generar` — lanza el pipeline completo ahora
- `/preview jueves` — genera el preview de un día
- `/ayuda` — lista de comandos

### Arranque automático (systemd)

```bash
sudo cp deploy/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now meraki-scheduler meraki-comandos
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

CLOUDINARY_CLOUD_NAME=
CLOUDINARY_API_KEY=
CLOUDINARY_API_SECRET=

DRY_RUN=true
APPROVAL_WINDOW_HOURS=2
MAX_REGENERATIONS=3
```

---

## Detalles de funcionamiento

- **Anti-repetición**: los captions publicados quedan en `state/historial.json` y se pasan al modelo como prohibidos — no se repite la misma frase semana a semana.
- **Variedad de imagen**: cada generación usa una seed aleatoria (guardada en el plan); al regenerar desde Telegram la imagen sale distinta.
- **Cloudinary**: antes de publicar en IG/FB la imagen se sube automáticamente y se usa su URL pública (Meta lo exige).
- **Validación al arrancar**: `config_check` revisa `.env` y ficheros; en producción (`DRY_RUN=false`) los errores bloquean el pipeline, en pruebas solo avisan.
- **Mantenimiento**: las imágenes de `output/` con más de 30 días se borran solas; los logs rotan a los 5 MB.

---

## Pendiente para producción

- Credenciales Meta Graph API (las tiene el propietario del bar)
- Credenciales Twitter/X si se quiere activar (`PUBLISH_TWITTER=false` por defecto)
