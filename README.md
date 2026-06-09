# meraki-bot

Automatización de redes sociales para **Meraki Bar & Cocktails** (Bilbao).

Cada lunes genera las publicaciones de la semana, las manda al móvil para aprobarlas y las publica en Instagram, Facebook y Twitter.

---

## Cómo funciona

El bot arranca cada lunes a las 9:00 y hace esto por cada día de la semana:

1. Planifica el contenido según la temática del día (mojitos, pintxopote, tortillas...)
2. Escribe el caption
3. Genera la imagen de fondo con IA
4. Monta la story (1080×1920) y el feed (1080×1080)
5. Manda un preview al móvil vía Telegram con botón de publicar o regenerar
6. Si no hay respuesta en 2 horas, publica solo

El bar está cerrado lunes y martes. Los miércoles, jueves y viernes rotan cada semana para no saturar.

---

## Tecnología

- **Ollama + llama3.1:8b** — planificación y redacción de captions
- **SDXL-Turbo** — generación de imágenes
- **Pillow** — composición de stories y feeds
- **Telegram Bot** — aprobación con botones inline
- **Meta Graph API** — publicación en Instagram y Facebook
- **Tweepy** — publicación en Twitter/X
- **APScheduler** — cron semanal

> Ollama y SDXL no caben en VRAM al mismo tiempo. El pipeline los usa en secuencia.

---

## Requisitos

- Ubuntu / WSL2, Python 3.14
- GPU NVIDIA con 8 GB VRAM mínimo
- Ollama corriendo localmente con llama3.1:8b
- Bot de Telegram configurado
- Credenciales de Meta Graph API y Twitter/X

---

## Instalación

```bash
git clone git@github.com:urki97/meraki-bot.git
cd meraki-bot

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# rellenar .env con los tokens
```

---

## Uso

```bash
source .venv/bin/activate

# Scheduler semanal (lunes 9:00)
python core/scheduler.py

# Ejecutar ahora sin esperar al lunes
python core/scheduler.py --ahora

# Generar preview de un día concreto
python generar_preview.py miercoles
python generar_preview.py jueves
python generar_preview.py viernes

# Tests (sin GPU ni credenciales)
python -m pytest tests/ -v
```

---

## Configuración

Copia `.env.example` a `.env` y rellena los valores:

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

DRY_RUN=true   # cambiar a false cuando esté todo listo
```

---

## Estructura

```
meraki-bot/
├── agents/
│   ├── planner.py       # plan semanal
│   ├── copy_agent.py    # captions
│   ├── image_agent.py   # imágenes con SDXL-Turbo
│   └── compositor.py    # montaje story y feed
├── core/
│   ├── scheduler.py     # cron semanal
│   ├── approval.py      # aprobación por Telegram
│   └── publisher.py     # publicación multi-plataforma
├── config/
│   ├── pautas.yaml      # tono, temáticas, hashtags
│   └── calendar.yaml    # eventos y temporadas
└── assets/
    ├── logo.png
    └── fonts/
```

---

## Estado

El bot está en desarrollo activo. DRY_RUN=true por defecto — no publica nada hasta configurar las credenciales.

Pendiente antes de ir a producción:
- Credenciales Meta Graph API (las gestiona el propietario del bar)
- CDN para subir las imágenes antes de publicarlas en Instagram
- Credenciales Twitter/X (opcional, PUBLISH_TWITTER=false por ahora)
