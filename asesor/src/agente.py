"""El cerebro: llamadas a la API de Anthropic con tool calling.

QUÉ: un bucle agéntico manual. Se manda la conversación al modelo; si
responde pidiendo tools (stop_reason == "tool_use"), se ejecutan con
tools.ejecutar(), se le devuelven los resultados y se repite. Cuando
responde con texto normal (end_turn), se devuelve al usuario.
POR QUÉ bucle manual y no el tool-runner del SDK: control fino del
historial, del límite de iteraciones y de los refusals — lo que necesita
un bot que corre 24/7 sin nadie mirando.

Particularidades de claude-fable-5:
- El razonamiento (thinking) va SIEMPRE activo: no se pasa el parámetro
  `thinking` (mandarlo desactivado da error 400). La profundidad se regula
  con output_config.effort.
- Sus clasificadores de seguridad pueden rechazar peticiones benignas
  (stop_reason == "refusal"). Por eso se activa el fallback de servidor:
  si Fable rechaza, la MISMA petición se re-sirve con claude-opus-4-8
  dentro de la misma llamada (el intento rechazado no se cobra).
- Los bloques thinking vuelven con texto vacío; hay que reenviarlos tal
  cual en el historial (por eso guardamos response.content sin tocar).
"""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import anthropic

from . import config, tools

log = logging.getLogger(__name__)

# El SDK lee ANTHROPIC_API_KEY del entorno por sí solo
_cliente = anthropic.Anthropic()

_DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")

_PROMPT_MINIMO = (
    "Eres un asesor personal por Telegram. Responde en español, breve y directo. "
    "Usa las tools para gestionar tareas, diario y decisiones del usuario."
)


def _prompt_sistema() -> str:
    """Se relee en cada llamada: puedes editar prompts/sistema.md sin reiniciar."""
    try:
        with open(config.PROMPT_PATH, encoding="utf-8") as f:
            texto = f.read().strip()
        return texto or _PROMPT_MINIMO
    except OSError:
        log.warning("No se pudo leer %s; uso el prompt mínimo", config.PROMPT_PATH)
        return _PROMPT_MINIMO


def _sistema() -> list[dict]:
    """Dos bloques: el prompt estable (cacheable) y la fecha (volátil).

    El prompt caching funciona por prefijo exacto: si la fecha estuviera
    dentro del bloque grande, cada día invalidaría toda la cache. Separada
    al final, la parte grande se sirve de cache (~10x más barata).
    """
    ahora = datetime.now(ZoneInfo(config.TZ))
    fecha = f"Hoy es {_DIAS[ahora.weekday()]} {ahora:%d/%m/%Y} y son las {ahora:%H:%M} ({config.TZ})."
    return [
        {"type": "text", "text": _prompt_sistema(), "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": fecha},
    ]


def conversar(historial: list, mensaje_usuario: str) -> tuple[str, list]:
    """Un turno completo de conversación. Devuelve (respuesta, historial_nuevo)."""
    mensajes = list(historial) + [{"role": "user", "content": mensaje_usuario}]

    for _ in range(config.MAX_ITERACIONES):
        respuesta = _cliente.beta.messages.create(
            model=config.MODEL_ID,
            max_tokens=config.MAX_TOKENS,
            # Fallback de servidor: si Fable rechaza por seguridad, Opus 4.8
            # atiende la misma petición en la misma llamada.
            betas=["server-side-fallback-2026-06-01"],
            fallbacks=[{"model": "claude-opus-4-8"}],
            output_config={"effort": config.EFFORT},
            system=_sistema(),
            tools=tools.TOOLS,
            messages=mensajes,
        )

        if respuesta.stop_reason == "refusal":
            # Rechazado incluso por el fallback. No contaminamos el historial.
            log.warning("Refusal definitivo: %s", getattr(respuesta, "stop_details", None))
            return (
                "⚠️ El modelo ha rechazado esta petición por sus filtros de seguridad. "
                "Prueba a reformularla.",
                list(historial),
            )

        for bloque in respuesta.content:
            if bloque.type == "fallback":
                log.info("Fallback activado: %s rechazó, %s continuó",
                         bloque.from_.model, bloque.to.model)

        # Se guarda el content COMPLETO (texto + tool_use + thinking):
        # la API exige recibir de vuelta exactamente lo que devolvió.
        mensajes.append({"role": "assistant", "content": respuesta.content})

        if respuesta.stop_reason == "tool_use":
            resultados = []
            for bloque in respuesta.content:
                if bloque.type == "tool_use":
                    salida, es_error = tools.ejecutar(bloque.name, dict(bloque.input))
                    resultados.append({
                        "type": "tool_result",
                        "tool_use_id": bloque.id,
                        "content": salida,
                        "is_error": es_error,
                    })
            # Todos los tool_result del turno van juntos en UN mensaje user
            mensajes.append({"role": "user", "content": resultados})
            continue

        break
    else:
        log.error("Bucle agéntico agotado tras %d iteraciones", config.MAX_ITERACIONES)
        return ("⚠️ Me he liado encadenando demasiadas tools. Vuelve a pedírmelo.", mensajes)

    texto = "\n".join(b.text for b in respuesta.content if b.type == "text").strip()
    log.info("Respuesta de %s (stop=%s, out=%s tokens)",
             respuesta.model, respuesta.stop_reason, respuesta.usage.output_tokens)
    return (texto or "Hecho ✅", mensajes)


def generar(prompt: str) -> str:
    """Petición puntual sin historial. La usan los jobs del scheduler."""
    texto, _ = conversar([], prompt)
    return texto
