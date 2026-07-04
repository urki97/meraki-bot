"""Memoria conversacional de corto plazo, en RAM y por chat.

QUÉ: la API de Anthropic es sin estado — hay que reenviar la conversación
entera en cada llamada. Este módulo guarda ese hilo por chat_id.
POR QUÉ en RAM y no en SQLite: la memoria "de verdad" (tareas, diario,
decisiones) ya persiste en la base de datos; el hilo conversacional es
desechable. Si el bot se reinicia solo se pierde el contexto del chat en
curso, nunca los datos. Además los bloques que devuelve el SDK (thinking,
tool_use) deben reenviarse intactos, y serializarlos a disco es frágil.
"""

from . import config

_historiales: dict[int, list] = {}


def obtener(chat_id: int) -> list:
    return list(_historiales.get(chat_id, []))


def guardar(chat_id: int, mensajes: list) -> None:
    _historiales[chat_id] = _recortar(mensajes)


def reset(chat_id: int) -> None:
    _historiales.pop(chat_id, None)


def _recortar(mensajes: list) -> list:
    """Limita el historial cortando SIEMPRE en un mensaje humano.

    No se puede cortar por cualquier sitio: un tool_result cuyo tool_use
    anterior se ha recortado hace que la API devuelva 400. Los mensajes de
    rol "user" con content de tipo str son siempre entrada humana (los
    tool_result van como listas), así que son puntos de corte seguros.
    """
    if len(mensajes) <= config.MAX_HISTORIAL:
        return mensajes
    inicio = len(mensajes) - config.MAX_HISTORIAL
    while inicio < len(mensajes):
        m = mensajes[inicio]
        if m.get("role") == "user" and isinstance(m.get("content"), str):
            return mensajes[inicio:]
        inicio += 1
    # Sin punto de corte seguro a la vista: mejor empezar de cero que un 400
    return []
