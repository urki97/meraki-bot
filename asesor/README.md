# Asesor personal (Telegram + Claude + Whisper)

Bot de Telegram que actúa de asesor personal: recibe texto y notas de voz
(transcritas con faster-whisper en GPU), razona con `claude-fable-5` vía
tool calling, persiste tareas/diario/decisiones en SQLite y manda avisos
proactivos con APScheduler (Europe/Madrid).

## Arranque

```bash
cd asesor
cp .env.example .env       # y rellena ANTHROPIC_API_KEY, TELEGRAM_BOT_TOKEN
docker compose build
docker compose up -d
docker compose logs -f asesor
```

Si no sabes tu `TELEGRAM_USER_ID`: arranca con `TELEGRAM_USER_ID=0`, mándale
`/start` al bot, copia el ID que te devuelve al `.env` y `docker compose up -d`
otra vez.

## Jobs programados

| Hora (Europe/Madrid) | Job |
|---|---|
| 08:00 diario | Brief matutino (tareas + deadlines + diario de ayer, redactado por el agente) |
| 12:00 diario | Tareas envejecidas (>3 días sin tocar) |
| 16:00 diario | Deadlines a ≤48h o vencidos (texto plano, funciona sin API) |
| Dom 20:00 | Retro semanal |

## Checklist si algo falla

**Voz**
- `docker compose exec asesor nvidia-smi` → si falla, Docker no ve la GPU
  (Docker Desktop → Settings → Resources → WSL integration, y driver NVIDIA en Windows).
- La primera nota de voz tarda: descarga ~3GB de modelo (míralo en los logs).
- Error de cuDNN/cublas → la imagen base debe ser `-cudnn-runtime`, no `-runtime`.
- Sin GPU: `WHISPER_DEVICE=cpu` + `WHISPER_COMPUTE=int8` en `.env`.

**Tool calling / agente**
- En los logs debe aparecer `🔧 crear_tarea(...) OK` cuando le pides cosas.
- `TypeError` en `messages.create` → SDK viejo: rebuild (`docker compose build --no-cache`).
- 400 `invalid_request_error` en TODAS las peticiones → tu organización tiene
  zero-data-retention; `claude-fable-5` exige retención de 30 días. Cambia la
  config de la org o usa `MODEL_ID=claude-opus-4-8`.
- Respuestas lentas: baja `EFFORT=low` (fable-5 con effort alto puede tardar minutos).

**Volumen / BD**
- Debe existir `./data/asesor.db` en el host tras el primer mensaje.
- Si la BD "se vacía" al recrear el contenedor, el volumen no está montado:
  revisa el bloque `volumes:` del compose.

**Zona horaria**
- `docker compose exec asesor date` debe dar hora de Madrid.
- En los logs de arranque, cada job imprime su próxima ejecución: comprueba
  que el brief diga 08:00+01:00 (o +02:00 en verano).
