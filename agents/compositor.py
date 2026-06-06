"""
Compositor v2: monta la story y el feed con diseño editorial.

Layout inspirado en el estilo del bar:
  - Titular grande y dominante en el tercio superior
  - Subtítulo / info en bloque inferior con overlay
  - Logo Meraki en esquina superior izquierda
  - Dos formatos de salida:
      story: 1080x1920 (Instagram/Facebook Stories)
      feed:  1080x1080 (Instagram/Facebook Feed, Twitter)
"""

import logging
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

logger = logging.getLogger("compositor")

BASE_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = BASE_DIR / "assets"
FONTS_DIR = ASSETS_DIR / "fonts"
OUTPUT_DIR = BASE_DIR / "output"

# Dimensiones
STORY_W, STORY_H = 1080, 1920
FEED_W,  FEED_H  = 1080, 1080

# Colores
BLANCO       = (255, 255, 255, 255)
BLANCO_SUAVE = (235, 235, 235, 220)
NEGRO        = (0, 0, 0, 255)
OVERLAY_TOP  = (0, 0, 0, 160)   # overlay superior para logo
OVERLAY_BOT  = (0, 0, 0, 210)   # overlay inferior para texto info


def _fuente(tamanyo: int, negrita: bool = False) -> ImageFont.FreeTypeFont:
    """Carga la mejor fuente disponible en el sistema."""
    candidatos = (
        [
            FONTS_DIR / "Inter-Bold.ttf",
            FONTS_DIR / "Roboto-Bold.ttf",
            Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
            Path("/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf"),
        ] if negrita else [
            FONTS_DIR / "Inter-Regular.ttf",
            FONTS_DIR / "Roboto-Regular.ttf",
            Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            Path("/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf"),
        ]
    )
    for ruta in candidatos:
        if ruta.exists():
            try:
                return ImageFont.truetype(str(ruta), tamanyo)
            except Exception:
                continue
    return ImageFont.load_default(size=tamanyo)


def _escalar_recortar(img: Image.Image, w: int, h: int) -> Image.Image:
    """Escala y recorta centrado para llenar exactamente w×h."""
    ratio_dest = w / h
    ratio_src  = img.width / img.height
    if ratio_src > ratio_dest:
        nuevo_h = h
        nuevo_w = int(img.width * h / img.height)
    else:
        nuevo_w = w
        nuevo_h = int(img.height * w / img.width)
    img = img.resize((nuevo_w, nuevo_h), Image.LANCZOS)
    left = (nuevo_w - w) // 2
    top  = (nuevo_h - h) // 2
    return img.crop((left, top, left + w, top + h))


def _overlay_rect(canvas: Image.Image, x0: int, y0: int, x1: int, y1: int, color: tuple) -> None:
    """Dibuja un rectángulo semitransparente sobre el canvas RGBA."""
    rect = Image.new("RGBA", (x1 - x0, y1 - y0), color)
    canvas.paste(rect, (x0, y0), rect)


def _texto_centrado(draw: ImageDraw.Draw, texto: str, y: int, fuente, ancho_max: int,
                    color=BLANCO, sombra: bool = True) -> int:
    """
    Dibuja texto centrado horizontalmente. Devuelve la Y final tras el texto.
    Aplica sombra si se indica.
    """
    bbox = fuente.getbbox(texto)
    tw = bbox[2] - bbox[0]
    x = (ancho_max - tw) // 2
    if sombra:
        draw.text((x + 3, y + 3), texto, font=fuente, fill=(0, 0, 0, 180))
    draw.text((x, y), texto, font=fuente, fill=color)
    return y + (bbox[3] - bbox[1]) + 10


def _bloque_texto_multilínea(
    draw: ImageDraw.Draw,
    texto: str,
    y_inicio: int,
    fuente,
    ancho_max: int,
    chars_por_linea: int = 18,
    espaciado: int = 14,
    color=BLANCO,
) -> int:
    """Dibuja un bloque de texto multilínea centrado. Devuelve Y final."""
    lineas = textwrap.wrap(texto, width=chars_por_linea)
    y = y_inicio
    for linea in lineas:
        y = _texto_centrado(draw, linea, y, fuente, ancho_max, color=color)
        y += espaciado
    return y


def _pegar_logo(canvas: Image.Image, logo_path: Path, ancho: int, x: int, y: int) -> None:
    """Pega el logo redimensionado en la posición indicada."""
    if not logo_path.exists():
        logger.warning(f"Logo no encontrado: {logo_path}")
        return
    logo = Image.open(logo_path).convert("RGBA")
    alto = int(logo.height * ancho / logo.width)
    logo = logo.resize((ancho, alto), Image.LANCZOS)
    canvas.paste(logo, (x, y), logo)


# ── Story 1080×1920 ───────────────────────────────────────────────────────────

def montar_story(
    image_path: Path | str,
    caption: str,
    hashtags: list[str],
    fecha: str,
    dia_semana: str,
    titulo: str | None = None,
    subtitulo: str | None = None,
    logo_path: Path | str | None = None,
    output_path: Path | str | None = None,
) -> Path:
    """
    Monta la story 1080×1920.

    Layout:
      - Franja superior (15%): overlay oscuro + logo Meraki
      - Zona central (55%): imagen sin overlay — foto protagonista
      - Franja inferior (30%): overlay oscuro + título grande + caption + hashtags

    Args:
        titulo:    titular grande (si None, usa el tema del día en mayúsculas)
        subtitulo: línea secundaria bajo el titular
    """
    W, H = STORY_W, STORY_H
    logo_path = Path(logo_path) if logo_path else ASSETS_DIR / "logo.png"
    if output_path is None:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        output_path = OUTPUT_DIR / f"{fecha}_{dia_semana}_story.jpg"
    output_path = Path(output_path)

    # 1. Base
    base = Image.open(image_path).convert("RGBA")
    base = _escalar_recortar(base, W, H)

    # 2. Overlay inferior (30% inferior)
    franja_bot_y = int(H * 0.70)
    _overlay_rect(base, 0, franja_bot_y, W, H, OVERLAY_BOT)

    # 3. Overlay superior (13% superior) para el logo
    franja_top_h = int(H * 0.13)
    _overlay_rect(base, 0, 0, W, franja_top_h, OVERLAY_TOP)

    draw = ImageDraw.Draw(base)

    # 4. Logo en esquina superior izquierda
    _pegar_logo(base, logo_path, ancho=140, x=40, y=20)

    # 5. Título grande en el inicio de la franja inferior
    y = franja_bot_y + 40
    if titulo:
        fuente_titulo = _fuente(110, negrita=True)
        lineas_titulo = textwrap.wrap(titulo.upper(), width=12)
        for linea in lineas_titulo:
            y = _texto_centrado(draw, linea, y, fuente_titulo, W)
            y += 8
        y += 20

    # 6. Caption en tamaño mediano
    fuente_caption = _fuente(52, negrita=False)
    lineas = textwrap.wrap(caption, width=22)
    for linea in lineas[:4]:   # máx 4 líneas para no saturar
        y = _texto_centrado(draw, linea, y, fuente_caption, W, color=BLANCO_SUAVE)
        y += 6

    # 7. Hashtags pequeños
    y += 20
    fuente_hash = _fuente(38)
    texto_hash = "  ".join(hashtags)
    _texto_centrado(draw, texto_hash, y, fuente_hash, W, color=(180, 180, 180, 200))

    # 8. Guardar
    base.convert("RGB").save(output_path, "JPEG", quality=92, optimize=True)
    logger.info(f"Story guardada: {output_path} ({output_path.stat().st_size // 1024} KB)")
    return output_path


# ── Feed 1080×1080 ────────────────────────────────────────────────────────────

def montar_feed(
    image_path: Path | str,
    caption: str,
    hashtags: list[str],
    fecha: str,
    dia_semana: str,
    titulo: str | None = None,
    logo_path: Path | str | None = None,
    output_path: Path | str | None = None,
) -> Path:
    """
    Monta imagen cuadrada 1080×1080 para feed de Instagram/Facebook/Twitter.

    Layout:
      - Imagen de fondo recortada a cuadrado
      - Overlay inferior (35%) con título + caption corto
      - Logo esquina superior izquierda pequeño
    """
    W, H = FEED_W, FEED_H
    logo_path = Path(logo_path) if logo_path else ASSETS_DIR / "logo.png"
    if output_path is None:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        output_path = OUTPUT_DIR / f"{fecha}_{dia_semana}_feed.jpg"
    output_path = Path(output_path)

    base = Image.open(image_path).convert("RGBA")
    base = _escalar_recortar(base, W, H)

    # Overlay inferior (35%)
    franja_bot_y = int(H * 0.65)
    _overlay_rect(base, 0, franja_bot_y, W, H, OVERLAY_BOT)

    # Overlay superior (10%)
    _overlay_rect(base, 0, 0, W, int(H * 0.10), OVERLAY_TOP)

    draw = ImageDraw.Draw(base)

    # Logo
    _pegar_logo(base, logo_path, ancho=100, x=30, y=15)

    y = franja_bot_y + 30

    # Título
    if titulo:
        fuente_titulo = _fuente(88, negrita=True)
        lineas_titulo = textwrap.wrap(titulo.upper(), width=14)
        for linea in lineas_titulo[:2]:
            y = _texto_centrado(draw, linea, y, fuente_titulo, W)
            y += 6
        y += 15

    # Caption corto (máx 2 líneas en el feed)
    fuente_caption = _fuente(44)
    lineas = textwrap.wrap(caption, width=26)
    for linea in lineas[:2]:
        y = _texto_centrado(draw, linea, y, fuente_caption, W, color=BLANCO_SUAVE)
        y += 4

    # Hashtags
    y += 12
    fuente_hash = _fuente(32)
    _texto_centrado(draw, "  ".join(hashtags), y, fuente_hash, W, color=(160, 160, 160, 200))

    base.convert("RGB").save(output_path, "JPEG", quality=92, optimize=True)
    logger.info(f"Feed guardado: {output_path} ({output_path.stat().st_size // 1024} KB)")
    return output_path


def montar_ambos(
    image_path: Path | str,
    caption: str,
    hashtags: list[str],
    fecha: str,
    dia_semana: str,
    titulo: str | None = None,
    logo_path: Path | str | None = None,
) -> dict[str, Path]:
    """
    Genera story (1080×1920) y feed (1080×1080) en una sola llamada.
    Devuelve {'story': Path, 'feed': Path}.
    """
    story = montar_story(image_path, caption, hashtags, fecha, dia_semana,
                         titulo=titulo, logo_path=logo_path)
    feed  = montar_feed(image_path, caption, hashtags, fecha, dia_semana,
                        titulo=titulo, logo_path=logo_path)
    return {"story": story, "feed": feed}


if __name__ == "__main__":
    import os
    from dotenv import load_dotenv

    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        level=logging.INFO,
    )
    load_dotenv(BASE_DIR / ".env")

    imagen_base = OUTPUT_DIR / "2026-06-04_miercoles_base.png"
    if not imagen_base.exists():
        logger.info("Creando imagen base de prueba...")
        img = Image.new("RGB", (1024, 1024), (20, 10, 30))
        draw = ImageDraw.Draw(img)
        draw.ellipse([200, 200, 800, 800], fill=(60, 30, 15))
        imagen_base.parent.mkdir(parents=True, exist_ok=True)
        img.save(imagen_base)

    rutas = montar_ambos(
        image_path=imagen_base,
        caption="El miércoles es de mojito. Sin discusión. Ven a Meraki.",
        hashtags=["#MiercolesDelMojito", "#MerakiBilbao", "#Santutxu"],
        fecha="2026-06-04",
        dia_semana="miercoles",
        titulo="Miércoles de Mojitos",
    )

    for formato, ruta in rutas.items():
        with Image.open(ruta) as img:
            print(f"{formato}: {ruta.name} — {img.size[0]}×{img.size[1]} px — {ruta.stat().st_size // 1024} KB")
