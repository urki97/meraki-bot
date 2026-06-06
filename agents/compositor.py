"""
Compositor v3: story y feed con diseño editorial limpio.

Cambios v3:
  - Logo circular con máscara
  - Sin overlay oscuro sobre la foto — gradiente suave solo en franja de texto
  - Anton Regular para títulos (condensada, impactante, estilo cartelería)
  - Montserrat Regular/LightItalic para caption y hashtags
  - Dos formatos:
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
BLANCO_SUAVE = (230, 225, 215, 230)
DORADO       = (210, 170, 80, 230)
GRIS_HASH    = (180, 175, 165, 200)


def _fuente(tamanyo: int, negrita: bool = False, display: bool = False, italic: bool = False) -> ImageFont.FreeTypeFont:
    """Carga la fuente más adecuada según estilo."""
    if display:
        # Anton: condensada e impactante para títulos
        candidatos = [
            FONTS_DIR / "Anton-Regular.ttf",
            FONTS_DIR / "Montserrat-Black.ttf",
            Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
        ]
    elif negrita:
        candidatos = [
            FONTS_DIR / "Montserrat-Bold.ttf",
            Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
        ]
    elif italic:
        candidatos = [
            FONTS_DIR / "Montserrat-LightItalic.ttf",
            Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
        ]
    else:
        candidatos = [
            FONTS_DIR / "Montserrat-Regular.ttf",
            Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
        ]
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


def _gradiente_vertical(canvas: Image.Image, y0: int, y1: int,
                         alpha_inicio: int, alpha_fin: int,
                         color_rgb: tuple = (0, 0, 0)) -> None:
    """Gradiente vertical semitransparente — la foto se ve a través."""
    h = y1 - y0
    for i in range(h):
        t = i / max(h - 1, 1)
        alpha = int(alpha_inicio + (alpha_fin - alpha_inicio) * t)
        franja = Image.new("RGBA", (canvas.width, 1), (*color_rgb, alpha))
        canvas.paste(franja, (0, y0 + i), franja)


def _pegar_logo_circular(canvas: Image.Image, logo_path: Path, diametro: int, x: int, y: int) -> None:
    """Pega el logo recortado en círculo con borde sutil."""
    if not logo_path.exists():
        logger.warning(f"Logo no encontrado: {logo_path}")
        return
    logo = Image.open(logo_path).convert("RGBA")
    logo = logo.resize((diametro, diametro), Image.LANCZOS)

    # Máscara circular
    mascara = Image.new("L", (diametro, diametro), 0)
    md = ImageDraw.Draw(mascara)
    md.ellipse([0, 0, diametro - 1, diametro - 1], fill=255)

    # Fondo circular semitransparente (para contraste sobre fotos claras)
    fondo = Image.new("RGBA", (diametro, diametro), (0, 0, 0, 100))
    fondo.paste(logo, (0, 0), logo)
    fondo.putalpha(mascara)

    # Borde dorado sutil
    borde_d = diametro + 4
    borde = Image.new("RGBA", (borde_d, borde_d), (0, 0, 0, 0))
    bd = ImageDraw.Draw(borde)
    bd.ellipse([0, 0, borde_d - 1, borde_d - 1], outline=(210, 170, 80, 160), width=2)
    canvas.paste(borde, (x - 2, y - 2), borde)
    canvas.paste(fondo, (x, y), fondo)


def _texto_con_sombra(draw: ImageDraw.Draw, texto: str, x: int, y: int,
                       fuente, color=BLANCO, sombra_offset: int = 3,
                       sombra_alpha: int = 200) -> None:
    """Dibuja texto con sombra desplazada para legibilidad."""
    draw.text((x + sombra_offset, y + sombra_offset), texto,
              font=fuente, fill=(0, 0, 0, sombra_alpha))
    draw.text((x, y), texto, font=fuente, fill=color)


def _texto_centrado_x(draw: ImageDraw.Draw, texto: str, y: int, fuente,
                       ancho_max: int, color=BLANCO) -> int:
    """Dibuja texto centrado horizontalmente con sombra. Devuelve Y final."""
    bbox = fuente.getbbox(texto)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    x = (ancho_max - tw) // 2
    _texto_con_sombra(draw, texto, x, y, fuente, color=color)
    return y + th + 10


def _linea_dorada(canvas: Image.Image, y: int, ancho_max: int, largo: int = 200) -> None:
    """Dibuja línea decorativa dorada centrada."""
    draw = ImageDraw.Draw(canvas)
    cx = ancho_max // 2
    draw.line([(cx - largo // 2, y), (cx + largo // 2, y)],
              fill=(210, 170, 80, 190), width=2)


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

    Layout v3:
      - Foto de fondo a pantalla completa sin overlay oscuro
      - Gradiente suave solo en franja superior (logo) e inferior (texto)
      - Logo circular con borde dorado, esquina superior izquierda
      - Título en Anton (condensada, uppercase) + línea dorada
      - Caption en Montserrat Regular + hashtags en itálica
    """
    W, H = STORY_W, STORY_H
    logo_path = Path(logo_path) if logo_path else ASSETS_DIR / "logo.png"
    if output_path is None:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        output_path = OUTPUT_DIR / f"{fecha}_{dia_semana}_story.jpg"
    output_path = Path(output_path)

    # 1. Foto de fondo a pantalla completa
    base = Image.open(image_path).convert("RGBA")
    base = _escalar_recortar(base, W, H)

    # 2. Gradiente suave superior (solo 15% — para que el logo sea legible)
    _gradiente_vertical(base, 0, int(H * 0.15), 140, 0)

    # 3. Gradiente suave inferior (solo 35% — gradiente de 0 a 175 alpha)
    # La foto sigue siendo visible, no oscuro total
    franja_bot_y = int(H * 0.65)
    _gradiente_vertical(base, franja_bot_y, H, 0, 175)

    draw = ImageDraw.Draw(base)

    # 4. Logo circular en esquina superior izquierda
    _pegar_logo_circular(base, logo_path, diametro=110, x=40, y=25)

    # 5. Título grande en Anton
    y = franja_bot_y + 40
    if titulo:
        fuente_titulo = _fuente(130, display=True)
        # Limpiar saltos de línea en título — pueden venir del yaml
        titulo_limpio = titulo.replace("\n", " ").strip()
        lineas_titulo = textwrap.wrap(titulo_limpio.upper(), width=12)
        for linea in lineas_titulo:
            y = _texto_centrado_x(draw, linea, y, fuente_titulo, W)
            y += 2
        # Línea dorada decorativa
        _linea_dorada(base, y + 8, W, largo=220)
        y += 28

    # 6. Caption en Montserrat Regular
    fuente_caption = _fuente(52)
    lineas_caption = textwrap.wrap(caption, width=22)
    for linea in lineas_caption[:4]:
        y = _texto_centrado_x(draw, linea, y, fuente_caption, W, color=BLANCO_SUAVE)
        y += 6

    # 7. Hashtags en itálica discreta
    y += 14
    fuente_hash = _fuente(34, italic=True)
    texto_hash = "  ".join(hashtags)
    _texto_centrado_x(draw, texto_hash, y, fuente_hash, W, color=GRIS_HASH)

    # 8. Guardar
    base.convert("RGB").save(output_path, "JPEG", quality=93, optimize=True)
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

    Layout v3:
      - Foto de fondo cuadrada, sin overlay total
      - Gradiente suave en zona inferior para texto
      - Logo circular pequeño esquina superior izquierda
    """
    W, H = FEED_W, FEED_H
    logo_path = Path(logo_path) if logo_path else ASSETS_DIR / "logo.png"
    if output_path is None:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        output_path = OUTPUT_DIR / f"{fecha}_{dia_semana}_feed.jpg"
    output_path = Path(output_path)

    base = Image.open(image_path).convert("RGBA")
    base = _escalar_recortar(base, W, H)

    # Gradiente superior (10%)
    _gradiente_vertical(base, 0, int(H * 0.10), 120, 0)

    # Gradiente inferior (38%)
    franja_bot_y = int(H * 0.62)
    _gradiente_vertical(base, franja_bot_y, H, 0, 170)

    draw = ImageDraw.Draw(base)

    # Logo circular
    _pegar_logo_circular(base, logo_path, diametro=80, x=25, y=18)

    y = franja_bot_y + 25

    # Título en Anton
    if titulo:
        fuente_titulo = _fuente(100, display=True)
        titulo_limpio = titulo.replace("\n", " ").strip()
        lineas_titulo = textwrap.wrap(titulo_limpio.upper(), width=14)
        for linea in lineas_titulo[:2]:
            y = _texto_centrado_x(draw, linea, y, fuente_titulo, W)
            y += 2
        _linea_dorada(base, y + 6, W, largo=180)
        y += 22

    # Caption (2 líneas máx en feed)
    fuente_caption = _fuente(40)
    lineas_caption = textwrap.wrap(caption, width=28)
    for linea in lineas_caption[:2]:
        y = _texto_centrado_x(draw, linea, y, fuente_caption, W, color=BLANCO_SUAVE)
        y += 4

    # Hashtags
    y += 10
    fuente_hash = _fuente(28, italic=True)
    _texto_centrado_x(draw, "  ".join(hashtags), y, fuente_hash, W, color=GRIS_HASH)

    base.convert("RGB").save(output_path, "JPEG", quality=93, optimize=True)
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
