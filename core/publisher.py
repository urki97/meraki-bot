"""
Publisher: publica la story en Instagram via Meta Graph API.
Con DRY_RUN=true simula la publicación sin llamadas reales.
Cuando lleguen las credenciales, basta con poner DRY_RUN=false en .env.

Flujo de publicación en Instagram (2 pasos obligatorios):
  1. POST /media          → sube la imagen y crea un container
  2. POST /media_publish  → publica el container creado
"""

import logging
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

logger = logging.getLogger("publisher")

META_API_BASE = "https://graph.facebook.com/v19.0"

# Backoff exponencial para reintentos: 1min, 5min, 15min
BACKOFF_SEGUNDOS = [60, 300, 900]


def _dry_run_activo() -> bool:
    return os.getenv("DRY_RUN", "true").lower() in ("true", "1", "yes")


def _credenciales() -> tuple[str, str]:
    """Devuelve (ig_user_id, access_token). Lanza ValueError si faltan."""
    ig_user_id = os.getenv("IG_USER_ID", "")
    access_token = os.getenv("IG_ACCESS_TOKEN", "")
    if not ig_user_id or not access_token:
        raise ValueError(
            "Faltan credenciales Meta: IG_USER_ID y/o IG_ACCESS_TOKEN no configurados en .env"
        )
    return ig_user_id, access_token


def _subir_imagen_a_cdn(story_path: Path) -> str:
    """
    Meta Graph API requiere que la imagen esté en una URL pública.
    Por ahora se espera que el caller proporcione una URL o se use
    un hosting temporal. Este método es un placeholder documentado.

    En producción: subir la imagen a un bucket S3/R2/similar y
    devolver la URL pública antes de llamar a la API.
    """
    raise NotImplementedError(
        "Meta Graph API requiere URL pública para la imagen. "
        "Implementar subida a bucket S3/R2/similar antes de activar DRY_RUN=false."
    )


def _crear_container_media(
    ig_user_id: str,
    access_token: str,
    image_url: str,
    caption: str,
) -> str:
    """
    Paso 1: crea el container de media en Instagram.
    Devuelve el creation_id del container.
    """
    url = f"{META_API_BASE}/{ig_user_id}/media"
    payload = {
        "image_url": image_url,
        "caption": caption,
        "media_type": "IMAGE",
        "access_token": access_token,
    }

    respuesta = requests.post(url, data=payload, timeout=30)
    respuesta.raise_for_status()
    datos = respuesta.json()

    if "id" not in datos:
        raise RuntimeError(f"Meta API no devolvió container id: {datos}")

    return datos["id"]


def _publicar_container(
    ig_user_id: str,
    access_token: str,
    creation_id: str,
) -> str:
    """
    Paso 2: publica el container creado.
    Devuelve el media_id del post publicado.
    """
    url = f"{META_API_BASE}/{ig_user_id}/media_publish"
    payload = {
        "creation_id": creation_id,
        "access_token": access_token,
    }

    respuesta = requests.post(url, data=payload, timeout=30)
    respuesta.raise_for_status()
    datos = respuesta.json()

    if "id" not in datos:
        raise RuntimeError(f"Meta API no devolvió media_id: {datos}")

    return datos["id"]


def publicar_story(dia: dict, image_url: str | None = None) -> dict:
    """
    Publica la story del día en Instagram.

    Args:
        dia: entrada del weekly_plan con story_path, caption y hashtags
        image_url: URL pública de la imagen (requerida cuando DRY_RUN=false)

    Returns:
        dict con resultado: {'estado': 'publicado'|'simulado', 'media_id': str, ...}
    """
    fecha = dia.get("fecha", "desconocida")
    nombre_dia = dia.get("dia_semana", "dia")
    story_path = Path(dia.get("story_path", ""))
    caption = dia.get("caption", "")
    hashtags = " ".join(dia.get("hashtags", []))
    caption_completo = f"{caption}\n\n{hashtags}".strip()

    dry_run = _dry_run_activo()

    if dry_run:
        # ── Modo simulación ─────────────────────────────────────────────────
        logger.info(f"[DRY_RUN] Simulando publicación de {nombre_dia} {fecha}")
        logger.info(f"[DRY_RUN] Story: {story_path}")
        logger.info(f"[DRY_RUN] Caption: {caption_completo[:80]}...")
        logger.info(f"[DRY_RUN] Pasos que ejecutaría:")
        logger.info(f"[DRY_RUN]   1. Subir imagen a CDN → obtener URL pública")
        logger.info(f"[DRY_RUN]   2. POST /{'{ig_user_id}'}/media → crear container")
        logger.info(f"[DRY_RUN]   3. POST /{'{ig_user_id}'}/media_publish → publicar")
        logger.info(f"[DRY_RUN] Publicación simulada correctamente ✓")

        return {
            "estado": "simulado",
            "fecha": fecha,
            "dia_semana": nombre_dia,
            "caption_preview": caption_completo[:100],
            "story_path": str(story_path),
            "media_id": "DRY_RUN_NO_ID",
        }

    # ── Modo real ─────────────────────────────────────────────────────────────
    ig_user_id, access_token = _credenciales()

    if not image_url:
        raise ValueError(
            "image_url requerida para publicación real. "
            "Sube story_path a un CDN antes de llamar a publicar_story()."
        )

    ultimo_error = None
    for intento, espera in enumerate(BACKOFF_SEGUNDOS, start=1):
        try:
            logger.info(f"Publicando {nombre_dia} {fecha} (intento {intento})...")

            # Paso 1: crear container
            creation_id = _crear_container_media(
                ig_user_id, access_token, image_url, caption_completo
            )
            logger.info(f"Container creado: {creation_id}")

            # Pequeña espera recomendada por Meta antes de publicar
            time.sleep(3)

            # Paso 2: publicar
            media_id = _publicar_container(ig_user_id, access_token, creation_id)
            logger.info(f"✅ Publicado correctamente — media_id: {media_id}")

            return {
                "estado": "publicado",
                "fecha": fecha,
                "dia_semana": nombre_dia,
                "media_id": media_id,
                "creation_id": creation_id,
            }

        except requests.HTTPError as e:
            ultimo_error = e
            status = e.response.status_code if e.response else "?"
            logger.error(f"HTTP {status} en intento {intento}: {e}")
            if intento < len(BACKOFF_SEGUNDOS):
                logger.info(f"Reintentando en {espera}s...")
                time.sleep(espera)

        except Exception as e:
            ultimo_error = e
            logger.error(f"Error inesperado en intento {intento}: {e}", exc_info=True)
            if intento < len(BACKOFF_SEGUNDOS):
                time.sleep(espera)

    raise RuntimeError(
        f"No se pudo publicar {nombre_dia} {fecha} tras {len(BACKOFF_SEGUNDOS)} intentos: {ultimo_error}"
    )


if __name__ == "__main__":
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        level=logging.INFO,
    )

    print("── Test publisher.py ──")
    print(f"DRY_RUN: {_dry_run_activo()}")
    print(f"IG_USER_ID: {'configurado' if os.getenv('IG_USER_ID') else 'NO configurado'}")
    print(f"IG_ACCESS_TOKEN: {'configurado' if os.getenv('IG_ACCESS_TOKEN') else 'NO configurado'}")

    # Día de prueba en modo DRY_RUN
    dia_prueba = {
        "fecha": "2026-06-04",
        "dia_semana": "miercoles",
        "caption": "El miércoles es de mojito. Sin discusión. Ven a Meraki.",
        "hashtags": ["#MiercolesDelMojito", "#MerakiBilbao", "#Santutxu"],
        "story_path": str(BASE_DIR / "output" / "2026-06-04_miercoles_story.png"),
    }

    resultado = publicar_story(dia_prueba)
    print(f"\nResultado: {resultado}")
