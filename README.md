# Meraki Bot

Bot de automatización de Instagram para **Meraki Bar & Cocktails** (@merakibilbao).  
Genera publicaciones semanales con IA, las envía para aprobación vía Telegram y las publica automáticamente.

---

## Qué hace

Cada lunes a las 9:00 el bot:

1. Genera un plan de 7 días consultando las pautas del bar
2. Para cada día: crea el caption (Ollama), genera la imagen (SDXL-Turbo) y monta la story (Pillow)
3. Envía un preview a Telegram con botones **✅ Publicar** / **❌ Regenerar**
4. Si no hay respuesta en 2 horas → publica automáticamente
5. Si se rechaza → regenera hasta 3 veces antes de descartar

---

## Requisitos

- Ubuntu / WSL2 con Python 3.12+
- GPU NVIDIA con ≥8 GB VRAM (RTX 4060 o similar)
- [Ollama](https://ollama.com) corriendo con `llama3.1:8b`
- Bot de Telegram ([@BotFather](https://t.me/BotFather))
- Credenciales de Meta Graph API (pendientes)

---

## Instalación

```bash
git clone <repo>
cd meraki_bot

# Crear entorno virtual
python3 -m venv .venv
source .venv/bin/activate

# Instalar dependencias en orden correcto
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
pip install -r requirements.txt

# Configurar credenciales
cp .env.example .env
# Editar .env con tus tokens
```

---

## Configuración (.env)

```env
TELEGRAM_BOT_TOKEN=tu_token_aqui
TELEGRAM_CHAT_ID=tu_chat_id_aqui

IG_USER_ID=           # pendiente — Meta Graph API
IG_ACCESS_TOKEN=      # pendiente — Meta Graph API

DRY_RUN=true          # false cuando tengas credenciales de Instagram
APPROVAL_WINDOW_HOURS=2
MAX_REGENERATIONS=3

OLLAMA_MODEL=llama3.1:8b
SDXL_MODEL=stabilityai/sdxl-turbo
```

---

## Uso

```bash
source .venv/bin/activate

# Lanzar el scheduler (cron lunes 9:00)
python core/scheduler.py

# Ejecutar el pipeline ahora mismo (para pruebas)
python core/scheduler.py --ahora

# Probar módulos por separado
python agents/planner.py
python agents/copy_agent.py
python agents/image_agent.py
python agents/compositor.py
python core/publisher.py

# Ejecutar tests (sin GPU ni credenciales)
python -m pytest tests/ -v
```

---

## Estructura

```
meraki_bot/
├── agents/
│   ├── planner.py       # plan semanal con Ollama
│   ├── copy_agent.py    # caption + hashtags con Ollama
│   ├── image_agent.py   # imagen base con SDXL-Turbo
│   └── compositor.py    # story 1080x1920 con Pillow
├── core/
│   ├── scheduler.py     # cron semanal APScheduler
│   ├── approval.py      # bot Telegram + lógica de aprobación
│   └── publisher.py     # Meta Graph API (DRY_RUN por defecto)
├── config/
│   ├── pautas.yaml      # tono, temáticas y hashtags del bar
│   └── calendar.yaml    # eventos y temporadas
├── assets/
│   └── logo.png         # logo placeholder (sustituir por el real)
├── state/
│   └── weekly_plan.json # estado persistente de la semana
├── output/              # stories generadas
└── logs/
    └── bot.log          # log de operaciones
```

---

## Gestión de VRAM (8 GB)

Ollama y SDXL-Turbo **no pueden estar en VRAM al mismo tiempo**.  
El pipeline los usa secuencialmente: primero genera el caption, libera VRAM, luego carga SDXL.

---

## Activar publicación real

Cuando tengas las credenciales de Meta:

1. Añade `IG_USER_ID` y `IG_ACCESS_TOKEN` al `.env`
2. Implementa la subida de imagen a un CDN en `core/publisher.py` (`_subir_imagen_a_cdn`)
3. Cambia `DRY_RUN=false` en el `.env`

---

## Logo

Sustituye `assets/logo.png` por el logo real del bar (fondo transparente, formato PNG).  
El compositor lo escala a 160px de ancho centrado en la parte inferior de la story.

---

## Ramas Git

| Rama | Uso |
|------|-----|
| `main` | Producción estable |
| `develop` | Integración de features |
| `feature/*` | Desarrollo de módulos |

Los merges a `main` los decide el usuario.
