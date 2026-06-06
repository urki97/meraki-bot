"""
Copy Agent: genera el caption y los hashtags para cada publicación.
Usa Ollama con el plan del día como contexto.
"""

import logging
import time
from pathlib import Path

import ollama
import yaml

logger = logging.getLogger("copy_agent")

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"


def _cargar_pautas() -> dict:
    with open(CONFIG_DIR / "pautas.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _construir_prompt(dia: dict, pautas: dict) -> str:
    """Construye el prompt para Ollama a partir del plan del día."""
    bar = pautas["bar"]
    tono = pautas["tono"]
    hashtags_fijos = " ".join(pautas["hashtags"]["fijos"])

    evitar = ", ".join(tono["evitar"])
    usar = ", ".join(tono["usar"])

    coctel_info = ""
    if dia.get("cocteles_temporada"):
        coctel_info = f"Cócteles de temporada sugeridos: {', '.join(dia['cocteles_temporada'][:3])}."

    evento_info = ""
    if dia.get("evento_especial"):
        evento_info = f"Evento especial esta semana: {dia['evento_especial']}."

    return f"""Eres el community manager de {bar['nombre']}, un bar de cócteles en {bar['direccion']}.
Slogan del bar: "{bar['slogan']}"
Instagram: {bar['instagram']} — cuenta pequeña con {bar['seguidores']} seguidores, tono cercano.

Escribe el caption para Instagram del {dia['dia_semana'].upper()}.

Información del día:
- Tema: {dia['tema']}
- Enfoque: {dia['enfoque']}
- Idea creativa: {dia['idea_creativa']}
- Temporada: {dia['temporada']}
{coctel_info}
{evento_info}

Reglas de tono (OBLIGATORIAS):
- Evitar: {evitar}
- Usar: {usar}
- Máximo 3 hashtags en total
- Hashtags fijos al final: {hashtags_fijos}
- Hashtag variable del día: {dia['hashtag_variable']}
- En español siempre
- Máximo 150 caracteres en el texto (sin contar hashtags)
- Sin inventar precios, eventos ni características no confirmadas

Responde ÚNICAMENTE con este formato JSON exacto, sin texto adicional:
{{
  "caption": "el texto del post aquí",
  "hashtags": ["#hashtag1", "#hashtag2", "#hashtag3"]
}}"""


def _parsear_respuesta(respuesta: str) -> dict:
    """Extrae el JSON de la respuesta de Ollama, tolerante a texto extra."""
    import json
    import re

    # Buscar el bloque JSON en la respuesta
    match = re.search(r'\{[^{}]*"caption"[^{}]*"hashtags"[^{}]*\}', respuesta, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    # Fallback: intentar parsear la respuesta completa
    try:
        return json.loads(respuesta.strip())
    except json.JSONDecodeError:
        pass

    # Último recurso: extraer manualmente
    caption_match = re.search(r'"caption"\s*:\s*"([^"]+)"', respuesta)
    hashtags_match = re.findall(r'"(#\w+)"', respuesta)

    if caption_match:
        return {
            "caption": caption_match.group(1),
            "hashtags": hashtags_match[:3] if hashtags_match else [],
        }

    raise ValueError(f"No se pudo parsear la respuesta de Ollama:\n{respuesta[:300]}")


def _acortar_para_twitter(caption: str, hashtags: list[str]) -> str:
    """
    Ajusta el caption a ≤280 caracteres para Twitter/X.
    Trunca el texto preservando el sentido y añade los hashtags al final.
    """
    hashtags_str = " ".join(hashtags)
    limite = 280 - len(hashtags_str) - 2  # 2 = salto de línea

    if len(caption) <= limite:
        return f"{caption}\n{hashtags_str}"

    # Truncar por palabra completa
    palabras = caption.split()
    texto = ""
    for palabra in palabras:
        candidato = f"{texto} {palabra}".strip()
        if len(candidato) + 3 > limite:   # +3 para "..."
            break
        texto = candidato

    return f"{texto}...\n{hashtags_str}"


def generar_caption(
    dia: dict,
    modelo: str = "llama3.1:8b",
    max_reintentos: int = 3,
) -> dict:
    """
    Genera caption y hashtags para el día dado.

    Args:
        dia: entrada del weekly_plan para un día concreto
        modelo: modelo Ollama a usar
        max_reintentos: intentos antes de lanzar excepción

    Returns:
        dict con keys 'caption' y 'hashtags'
    """
    pautas = _cargar_pautas()
    prompt = _construir_prompt(dia, pautas)

    ultimo_error = None
    for intento in range(1, max_reintentos + 1):
        try:
            logger.info(f"Generando caption para {dia['dia_semana']} (intento {intento})...")
            respuesta = ollama.generate(model=modelo, prompt=prompt)
            texto = respuesta["response"].strip()
            resultado = _parsear_respuesta(texto)

            # Validar que tiene los campos esperados
            if "caption" not in resultado or "hashtags" not in resultado:
                raise ValueError("Respuesta incompleta — faltan campos")

            # Asegurar que los hashtags fijos están incluidos
            fijos = pautas["hashtags"]["fijos"]
            for fijo in fijos:
                if fijo not in resultado["hashtags"]:
                    resultado["hashtags"].append(fijo)

            # Limitar a 3 hashtags máximo
            resultado["hashtags"] = resultado["hashtags"][:3]

            # Generar versión corta para Twitter (≤280 chars con hashtags)
            resultado["caption_twitter"] = _acortar_para_twitter(
                resultado["caption"], resultado["hashtags"]
            )

            logger.info(f"Caption OK: {resultado['caption'][:60]}...")
            return resultado

        except Exception as e:
            ultimo_error = e
            logger.warning(f"Intento {intento}/{max_reintentos} fallido: {e}")
            if intento < max_reintentos:
                time.sleep(10)

    raise RuntimeError(
        f"No se pudo generar caption para {dia['dia_semana']} tras {max_reintentos} intentos: {ultimo_error}"
    )


if __name__ == "__main__":
    import json
    import os
    from dotenv import load_dotenv

    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        level=logging.INFO,
    )

    load_dotenv(BASE_DIR / ".env")
    modelo = os.getenv("OLLAMA_MODEL", "llama3.1:8b")

    # Cargar plan existente o crear uno de ejemplo
    state_file = BASE_DIR / "state" / "weekly_plan.json"
    if state_file.exists():
        with open(state_file, encoding="utf-8") as f:
            plan = json.load(f)
        # Tomar el primer día del plan como prueba
        dia_prueba = next(iter(plan.values()))
    else:
        # Día de ejemplo sin necesitar el planner
        dia_prueba = {
            "fecha": "2026-06-04",
            "dia_semana": "miercoles",
            "tema": "Miércoles de mojitos",
            "enfoque": "promoción fija — mojitos a precio especial",
            "idea_creativa": "El miércoles es de mojito. Sin discusión.",
            "hashtag_variable": "#MiercolesDelMojito",
            "temporada": "Verano",
            "cocteles_temporada": ["mojito clásico", "daiquiri de mango"],
            "evento_especial": None,
        }

    print(f"\nGenerando caption para: {dia_prueba['dia_semana'].upper()}")
    print(f"Idea: {dia_prueba['idea_creativa']}\n")

    resultado = generar_caption(dia_prueba, modelo=modelo)

    print("── Resultado ──────────────────────────────────────────────")
    print(f"Caption  : {resultado['caption']}")
    print(f"Hashtags : {' '.join(resultado['hashtags'])}")
