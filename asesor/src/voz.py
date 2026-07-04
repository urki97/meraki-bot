"""Transcripción de notas de voz con faster-whisper (GPU).

QUÉ: carga perezosa del modelo Whisper y una función transcribir(ruta) → texto.
La primera nota de voz tarda más (descarga del modelo a ~/.cache y carga en
VRAM); las siguientes son rápidas porque el modelo se queda residente.
POR QUÉ faster-whisper: es Whisper reimplementado sobre CTranslate2, ~4x más
rápido que openai-whisper con el mismo acierto. Además decodifica el .oga/.ogg
de Telegram directamente (trae las librerías de ffmpeg embebidas vía PyAV),
así que no hace falta convertir el audio antes.
"""

import logging
import threading

from faster_whisper import WhisperModel

from . import config

log = logging.getLogger(__name__)

_modelo: WhisperModel | None = None
_candado = threading.Lock()  # dos notas de voz a la vez no deben cargar el modelo dos veces


def _obtener_modelo() -> WhisperModel:
    global _modelo
    with _candado:
        if _modelo is None:
            log.info("Cargando Whisper '%s' (device=%s, compute=%s)…",
                     config.WHISPER_MODEL, config.WHISPER_DEVICE, config.WHISPER_COMPUTE)
            _modelo = WhisperModel(
                config.WHISPER_MODEL,
                device=config.WHISPER_DEVICE,
                compute_type=config.WHISPER_COMPUTE,
            )
            log.info("Whisper cargado.")
    return _modelo


def transcribir(ruta: str) -> str:
    """Transcribe un fichero de audio y devuelve el texto plano."""
    segmentos, info = _obtener_modelo().transcribe(
        ruta,
        language=config.WHISPER_IDIOMA or None,  # None → autodetección de idioma
        vad_filter=True,  # recorta silencios: evita alucinaciones en las pausas
    )
    # `segmentos` es un generador: la transcripción real ocurre al iterarlo
    texto = " ".join(s.text.strip() for s in segmentos).strip()
    log.info("Transcritos %.1fs de audio: %r", info.duration, texto[:80])
    return texto
