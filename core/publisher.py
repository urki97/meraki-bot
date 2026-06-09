"""
Publisher: publica en Instagram, Facebook y Twitter/X.
Cada red se activa/desactiva con flags en .env.
Con DRY_RUN=true simula todo sin llamadas reales.

Flujo Instagram (Meta Graph API, 2 pasos):
  1. POST /{ig_user_id}/media        → crea container
  2. POST /{ig_user_id}/media_publish → publica

Flujo Facebook (misma Meta API):
  1. POST /{page_id}/photos           → sube y publica directo

Flujo Twitter/X (API v2 con tweepy):
  1. Subir imagen con media/upload
  2. Crear tweet con el media_id
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
BACKOFF = [60, 300, 900]   # segundos entre reintentos


# ── Helpers ───────────────────────────────────────────────────────────────────

def _dry_run() -> bool:
    return os.getenv("DRY_RUN", "true").lower() in ("true", "1", "yes")

def _activa(red: str) -> bool:
    return os.getenv(f"PUBLISH_{red.upper()}", "false").lower() in ("true", "1", "yes")

def _redes_activas() -> list[str]:
    return [r for r in ["instagram", "facebook", "twitter"] if _activa(r)]

def _con_backoff(fn, nombre: str):
    """Ejecuta fn con reintentos y backoff exponencial."""
    ultimo_error = None
    for intento, espera in enumerate(BACKOFF, start=1):
        try:
            return fn()
        except requests.HTTPError as e:
            ultimo_error = e
            logger.error(f"[{nombre}] HTTP {e.response.status_code if e.response else '?'} intento {intento}: {e}")
        except Exception as e:
            ultimo_error = e
            logger.error(f"[{nombre}] Error intento {intento}: {e}", exc_info=True)
        if intento < len(BACKOFF):
            logger.info(f"[{nombre}] Reintentando en {espera}s...")
            time.sleep(espera)
    raise RuntimeError(f"[{nombre}] Fallido tras {len(BACKOFF)} intentos: {ultimo_error}")


# ── Instagram ─────────────────────────────────────────────────────────────────

def publish_instagram(dia: dict, image_url: str) -> dict:
    """
    Publica en Instagram via Meta Graph API (2 pasos).
    Requiere image_url pública (subir a CDN antes de llamar).
    """
    if _dry_run():
        logger.info("[DRY_RUN][Instagram] Simularía: crear container → publicar")
        logger.info(f"[DRY_RUN][Instagram] caption: {dia.get('caption','')[:60]}...")
        return {"red": "instagram", "estado": "simulado", "media_id": "DRY_RUN"}

    ig_user_id  = os.getenv("IG_USER_ID", "")
    access_token = os.getenv("IG_ACCESS_TOKEN", "")
    if not ig_user_id or not access_token:
        raise ValueError("Faltan IG_USER_ID / IG_ACCESS_TOKEN en .env")

    caption_completo = _caption_completo(dia)

    def _publicar():
        # Paso 1: crear container
        r = requests.post(
            f"{META_API_BASE}/{ig_user_id}/media",
            data={"image_url": image_url, "caption": caption_completo,
                  "media_type": "IMAGE", "access_token": access_token},
            timeout=30,
        )
        r.raise_for_status()
        creation_id = r.json()["id"]
        logger.info(f"[Instagram] Container creado: {creation_id}")
        time.sleep(3)
        # Paso 2: publicar
        r2 = requests.post(
            f"{META_API_BASE}/{ig_user_id}/media_publish",
            data={"creation_id": creation_id, "access_token": access_token},
            timeout=30,
        )
        r2.raise_for_status()
        media_id = r2.json()["id"]
        logger.info(f"[Instagram] ✅ Publicado — media_id: {media_id}")
        return {"red": "instagram", "estado": "publicado", "media_id": media_id}

    return _con_backoff(_publicar, "Instagram")


# ── Facebook ──────────────────────────────────────────────────────────────────

def publish_facebook(dia: dict, image_url: str) -> dict:
    """
    Publica en Facebook usando la misma Meta API.
    El access_token debe tener permisos sobre la página.
    """
    if _dry_run():
        logger.info("[DRY_RUN][Facebook] Simularía: POST /{page_id}/photos")
        return {"red": "facebook", "estado": "simulado", "post_id": "DRY_RUN"}

    page_id      = os.getenv("FACEBOOK_PAGE_ID", "")
    access_token = os.getenv("IG_ACCESS_TOKEN", "")   # mismo token si la página está vinculada
    if not page_id or not access_token:
        raise ValueError("Faltan FACEBOOK_PAGE_ID / IG_ACCESS_TOKEN en .env")

    caption_completo = _caption_completo(dia)

    def _publicar():
        r = requests.post(
            f"{META_API_BASE}/{page_id}/photos",
            data={"url": image_url, "message": caption_completo, "access_token": access_token},
            timeout=30,
        )
        r.raise_for_status()
        post_id = r.json().get("post_id") or r.json().get("id")
        logger.info(f"[Facebook] ✅ Publicado — post_id: {post_id}")
        return {"red": "facebook", "estado": "publicado", "post_id": post_id}

    return _con_backoff(_publicar, "Facebook")


# ── Twitter / X ───────────────────────────────────────────────────────────────

def publish_twitter(dia: dict, feed_path: Path | str) -> dict:
    """
    Publica en Twitter/X usando tweepy v4 (API v2).
    Usa feed_path (1080×1080) porque las stories no se ven bien en Twitter.
    El caption es la versión corta ≤280 chars.
    """
    if _dry_run():
        logger.info("[DRY_RUN][Twitter] Simularía: upload media → create tweet")
        logger.info(f"[DRY_RUN][Twitter] tweet: {dia.get('caption_twitter','')[:60]}...")
        return {"red": "twitter", "estado": "simulado", "tweet_id": "DRY_RUN"}

    try:
        import tweepy
    except ImportError:
        raise RuntimeError("tweepy no instalado — ejecuta: pip install tweepy")

    api_key     = os.getenv("TWITTER_API_KEY", "")
    api_secret  = os.getenv("TWITTER_API_SECRET", "")
    acc_token   = os.getenv("TWITTER_ACCESS_TOKEN", "")
    acc_secret  = os.getenv("TWITTER_ACCESS_SECRET", "")

    if not all([api_key, api_secret, acc_token, acc_secret]):
        raise ValueError("Faltan credenciales Twitter en .env")

    texto = dia.get("caption_twitter") or _caption_twitter_fallback(dia)
    feed_path = Path(feed_path)

    def _publicar():
        # API v1.1 para subir media (v2 no soporta upload directo aún)
        auth = tweepy.OAuth1UserHandler(api_key, api_secret, acc_token, acc_secret)
        api_v1 = tweepy.API(auth)
        media = api_v1.media_upload(str(feed_path))
        logger.info(f"[Twitter] Media subida: {media.media_id}")

        # API v2 para crear el tweet
        client = tweepy.Client(
            consumer_key=api_key, consumer_secret=api_secret,
            access_token=acc_token, access_token_secret=acc_secret,
        )
        tweet = client.create_tweet(text=texto, media_ids=[media.media_id])
        tweet_id = tweet.data["id"]
        logger.info(f"[Twitter] ✅ Publicado — tweet_id: {tweet_id}")
        return {"red": "twitter", "estado": "publicado", "tweet_id": tweet_id}

    return _con_backoff(_publicar, "Twitter")


# ── Publicación coordinada ────────────────────────────────────────────────────

def publicar_story(dia: dict, image_url: str | None = None) -> dict:
    """
    Publica en todas las redes activas según los flags del .env.
    Coordina Instagram, Facebook y Twitter.

    Args:
        dia:       entrada del weekly_plan con story_path, feed_path, caption, etc.
        image_url: URL pública de la imagen (requerida para IG/FB en producción)

    Returns:
        dict con resultados por red: {'instagram': {...}, 'facebook': {...}, ...}
    """
    fecha      = dia.get("fecha", "?")
    nombre_dia = dia.get("dia_semana", "?")
    # Si el bot de Telegram sobreescribió los toggles para este post, usarlos
    override = dia.get("_redes_override")
    if override:
        redes = [r for r, v in override.items() if v]
    else:
        redes = _redes_activas()
    resultados = {}

    if not redes:
        logger.warning("Ninguna red activa en .env — no se publica nada")
        return {}

    logger.info(f"Publicando {nombre_dia} {fecha} en: {', '.join(redes)}")

    if _dry_run():
        logger.info(f"[DRY_RUN] Simulando publicación en {redes}")

    # Si IG o FB están activas y no hay URL, subir imagen a Cloudinary
    necesita_url = any(r in redes for r in ("instagram", "facebook"))
    if necesita_url and not image_url and not _dry_run():
        story_path = dia.get("story_path", "")
        if story_path and Path(story_path).exists():
            image_url = _subir_imagen_a_cdn(story_path)
        else:
            logger.error("No hay story_path disponible para subir a Cloudinary")

    if "instagram" in redes:
        try:
            resultados["instagram"] = publish_instagram(dia, image_url or "DRY_RUN_URL")
        except Exception as e:
            logger.error(f"Error Instagram: {e}")
            resultados["instagram"] = {"estado": "error", "error": str(e)}

    if "facebook" in redes:
        try:
            resultados["facebook"] = publish_facebook(dia, image_url or "DRY_RUN_URL")
        except Exception as e:
            logger.error(f"Error Facebook: {e}")
            resultados["facebook"] = {"estado": "error", "error": str(e)}

    if "twitter" in redes:
        feed_path = dia.get("feed_path", "")
        try:
            resultados["twitter"] = publish_twitter(dia, feed_path)
        except Exception as e:
            logger.error(f"Error Twitter: {e}")
            resultados["twitter"] = {"estado": "error", "error": str(e)}

    return resultados


# ── Cloudinary CDN ───────────────────────────────────────────────────────────

def _subir_imagen_a_cdn(image_path: str) -> str:
    """
    Sube la imagen a Cloudinary y devuelve la URL pública HTTPS.
    Meta Graph API necesita una URL accesible para crear el container de IG/FB.

    La imagen se guarda en la carpeta 'meraki/' de Cloudinary con el nombre
    del fichero como public_id, para mantener orden y evitar duplicados.
    """
    import cloudinary
    import cloudinary.uploader

    cloudinary.config(
        cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
        api_key=os.getenv("CLOUDINARY_API_KEY"),
        api_secret=os.getenv("CLOUDINARY_API_SECRET"),
        secure=True,
    )

    nombre = Path(image_path).stem  # ej. "2026-06-11_jueves_story"
    logger.info(f"Subiendo imagen a Cloudinary: {nombre}")

    resultado = cloudinary.uploader.upload(
        image_path,
        public_id=f"meraki/{nombre}",
        overwrite=True,
        resource_type="image",
    )

    url = resultado["secure_url"]
    logger.info(f"Imagen disponible en: {url}")
    return url


# ── Helpers internos ──────────────────────────────────────────────────────────

def _caption_completo(dia: dict) -> str:
    caption  = dia.get("caption", "")
    hashtags = " ".join(dia.get("hashtags", []))
    return f"{caption}\n\n{hashtags}".strip()

def _caption_twitter_fallback(dia: dict) -> str:
    """Genera versión Twitter truncada si caption_twitter no existe."""
    from agents.copy_agent import _acortar_para_twitter
    return _acortar_para_twitter(dia.get("caption", ""), dia.get("hashtags", []))


if __name__ == "__main__":
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        level=logging.INFO,
    )

    print("── Test publisher multi-plataforma ──")
    print(f"DRY_RUN     : {_dry_run()}")
    print(f"Redes activas (según .env): {_redes_activas()}")
    print()

    dia_prueba = {
        "fecha": "2026-06-04",
        "dia_semana": "miercoles",
        "caption": "El miércoles es de mojito. Sin discusión. Ven a Meraki.",
        "caption_twitter": "El miércoles es de mojito. Sin discusión.\n#MiercolesDelMojito #MerakiBilbao #Santutxu",
        "hashtags": ["#MiercolesDelMojito", "#MerakiBilbao", "#Santutxu"],
        "story_path": str(BASE_DIR / "output" / "2026-06-04_miercoles_story.jpg"),
        "feed_path":  str(BASE_DIR / "output" / "2026-06-04_miercoles_feed.jpg"),
    }

    resultados = publicar_story(dia_prueba)
    print("Resultados:")
    for red, res in resultados.items():
        print(f"  {red}: {res.get('estado')} — {res.get('media_id') or res.get('tweet_id') or res.get('post_id')}")

    if not resultados:
        print("  (ninguna red activa — activa PUBLISH_INSTAGRAM=true en .env)")
