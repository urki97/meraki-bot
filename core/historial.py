"""
Historial de publicaciones: registro persistente de lo ya publicado.

Sirve para dos cosas:
  1. Que el copy agent no repita captions de semanas anteriores
     (se le pasan los últimos como "prohibidos" en el prompt)
  2. Consultar qué se ha publicado y cuándo (comando /estado de Telegram)

Formato de state/historial.json: lista de entradas, la más reciente al final.
"""

import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("historial")

BASE_DIR = Path(__file__).resolve().parent.parent
HIST_FILE = BASE_DIR / "state" / "historial.json"

# Tamaño máximo del historial en disco — más que suficiente para un año
MAX_ENTRADAS = 200


def _cargar(ruta: Path | None = None) -> list[dict]:
    ruta = ruta or HIST_FILE
    if not ruta.exists():
        return []
    try:
        with open(ruta, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Historial ilegible ({e}) — se empieza de cero")
        return []


def _guardar(entradas: list[dict], ruta: Path | None = None) -> None:
    ruta = ruta or HIST_FILE
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(entradas[-MAX_ENTRADAS:], f, ensure_ascii=False, indent=2)


def registrar_publicacion(dia: dict, resultados: dict, ruta: Path | None = None) -> None:
    """
    Añade una entrada al historial tras publicar.
    Solo registra las redes cuyo estado fue 'publicado' (o 'simulado' en DRY_RUN,
    para poder probar el flujo completo sin credenciales).
    """
    redes_ok = [
        red for red, r in resultados.items()
        if isinstance(r, dict) and r.get("estado") in ("publicado", "simulado")
    ]
    if not redes_ok:
        return

    entradas = _cargar(ruta)
    entradas.append({
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "fecha": dia.get("fecha"),
        "dia_semana": dia.get("dia_semana"),
        "tema": dia.get("tema"),
        "caption": dia.get("caption"),
        "hashtags": dia.get("hashtags", []),
        "redes": redes_ok,
        "seed_imagen": dia.get("seed_imagen"),
    })
    _guardar(entradas, ruta)
    logger.info(f"Historial: registrada publicación de {dia.get('fecha')} en {redes_ok}")


def captions_recientes(n: int = 8, ruta: Path | None = None) -> list[str]:
    """Devuelve los últimos n captions publicados (para no repetirlos)."""
    entradas = _cargar(ruta)
    captions = [e["caption"] for e in entradas if e.get("caption")]
    return captions[-n:]


def ultimas(n: int = 10, ruta: Path | None = None) -> list[dict]:
    """Devuelve las últimas n entradas completas del historial."""
    return _cargar(ruta)[-n:]


if __name__ == "__main__":
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        level=logging.INFO,
    )

    print("\n── Historial de publicaciones ─────────────────────────────")
    entradas = ultimas(10)
    if not entradas:
        print("(vacío — aún no se ha publicado nada)")
    for e in entradas:
        redes = ", ".join(e.get("redes", []))
        print(f"\n{e['fecha']} ({e['dia_semana']}) → {redes}")
        print(f"  {e['caption']}")

    print(f"\nCaptions recientes para anti-repetición: {len(captions_recientes())}")
