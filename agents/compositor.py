"""
Compositor v4: story y feed con composición profesional de Instagram.

Principios aplicados:
  - Safe zones IG: evitar top/bottom 250px (zona de UI de la app)
  - Texto ≤1/5 de la imagen — sin abarrotar
  - Sin hashtags en la imagen (van en el caption del post)
  - Sin líneas decorativas — limpieza visual
  - Dos bloques máx: título grande + tagline corta (1 línea)
  - Logo circular pequeño en zona superior segura
  - Gradiente MUY suave — la foto se ve siempre
  - Dos formatos:
      story: 1080x1920 (Instagram/Facebook Stories)
      feed:  1080x1080 (Instagram/Facebook Feed, Twitter)
"""

import logging
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger("compositor")

BASE_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = BASE_DIR / "assets"
FONTS_DIR = ASSETS_DIR / "fonts"
OUTPUT_DIR = BASE_DIR / "output"

# Dimensiones
STORY_W, STORY_H = 1080, 1920
FEED_W,  FEED_H  = 1080, 1080

# Safe zones Instagram (pixeles a respetar)
STORY_SAFE_TOP    = 260   # zona de avatar + X
STORY_SAFE_BOTTOM = 250   # zona de respuesta

# Colores
BLANCO       = (255, 255, 255, 255)
BLANCO_SUAVE = (240, 235, 225, 235)


def _fuente(tamanyo: int, display: bool = False, italic: bool = False) -> ImageFont.FreeTypeFont:
    """Carga la fuente adecuada según el rol."""
    if display:
        # Anton: condensada, impactante, perfecta para títulos de bar
        candidatos = [
            FONTS_DIR / "Anton-Regular.ttf",
            FONTS_DIR / "Montserrat-Black.ttf",
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
    """Gradiente muy suave — la foto se ve a través."""
    h = y1 - y0
    for i in range(h):
        t = i / max(h - 1, 1)
        alpha = int(alpha_inicio + (alpha_fin - alpha_inicio) * t)
        franja = Image.new("RGBA", (canvas.width, 1), (*color_rgb, alpha))
        canvas.paste(franja, (0, y0 + i), franja)


def _logo_circular(canvas: Image.Image, logo_path: Path, diametro: int, x: int, y: int) -> None:
    """Pega el logo recortado en círculo con fondo semitransparente."""
    if not logo_path.exists():
        logger.warning(f"Logo no encontrado: {logo_path}")
        return
    logo = Image.open(logo_path).convert("RGBA")
    logo = logo.resize((diametro, diametro), Image.LANCZOS)

    # Fondo circular oscuro (contraste sobre cualquier fondo de foto)
    fondo = Image.new("RGBA", (diametro, diametro), (0, 0, 0, 0))
    mascara = Image.new("L", (diametro, diametro), 0)
    ImageDraw.Draw(mascara).ellipse([0, 0, diametro - 1, diametro - 1], fill=255)
    fondo.paste(logo, (0, 0), logo)
    fondo.putalpha(mascara)
    canvas.paste(fondo, (x, y), fondo)


def _texto_sombra(draw: ImageDraw.Draw, texto: str, x: int, y: int,
                   fuente, color=BLANCO) -> None:
    """Dibuja texto con sombra difusa para legibilidad sin overlay."""
    # Sombra en múltiples offsets para efecto difuso
    for dx, dy in [(2, 2), (3, 3), (-1, 2), (2, -1)]:
        draw.text((x + dx, y + dy), texto, font=fuente, fill=(0, 0, 0, 120))
    draw.text((x, y), texto, font=fuente, fill=color)


def _centrar_x(texto: str, fuente, ancho: int) -> int:
    """Devuelve la X para centrar el texto dado en el ancho indicado."""
    bbox = fuente.getbbox(texto)
    return (ancho - (bbox[2] - bbox[0])) // 2


def _altura_texto(texto: str, fuente) -> int:
    """Altura real del texto."""
    bbox = fuente.getbbox(texto)
    return bbox[3] - bbox[1]


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
    Monta la story 1080×1920 con composición profesional.

    Layout v4:
      - Foto a pantalla completa, sin overlay total
      - Gradiente suave solo en tercio inferior (foto visible a través)
      - Logo circular pequeño en safe zone superior
      - Título grande centrado (Anton) en zona inferior segura
      - Tagline corta (1 línea, Montserrat) bajo el título
      - Sin hashtags ni líneas decorativas
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

    # 2. Gradiente inferior muy suave (último 38%) — foto visible siempre
    grad_inicio = int(H * 0.62)
    _gradiente_vertical(base, grad_inicio, H, 0, 160)

    # 3. Gradiente mínimo superior (solo 12%) — para que el logo sea legible
    _gradiente_vertical(base, 0, int(H * 0.12), 90, 0)

    draw = ImageDraw.Draw(base)

    # 4. Logo circular en safe zone superior (y=40 — dentro del área de UI pero el logo sí va ahí)
    _logo_circular(base, logo_path, diametro=90, x=40, y=40)

    # 5. Bloque de texto en safe zone inferior
    # Safe zone inferior empieza en H - STORY_SAFE_BOTTOM = 1670
    # Colocamos el bloque 40px sobre ese límite → texto arranca en ~1350 y acaba antes de 1670
    fuente_titulo = _fuente(144, display=True)
    fuente_tagline = _fuente(52)

    # Preparar líneas del título (1-2 palabras por línea, max 10 chars)
    titulo_limpio = (titulo or dia_semana.upper()).replace("\n", " ").strip().upper()
    lineas_titulo = textwrap.wrap(titulo_limpio, width=10)[:3]

    # Calcular altura total del bloque para centrarlo verticalmente en la zona inferior
    alto_titulo = sum(_altura_texto(l, fuente_titulo) + 8 for l in lineas_titulo)

    # Primera línea de caption como tagline (sin hashtags, máx 32 chars)
    primera_frase = caption.split(".")[0].strip()
    if len(primera_frase) > 34:
        primera_frase = primera_frase[:32].rsplit(" ", 1)[0] + "…"
    alto_tagline = _altura_texto(primera_frase, fuente_tagline) + 8

    alto_total = alto_titulo + alto_tagline + 24
    y_inicio = int(H * 0.73)  # empieza al 73% — zona inferior con gradiente

    y = y_inicio

    # 6. Título
    for linea in lineas_titulo:
        x = _centrar_x(linea, fuente_titulo, W)
        _texto_sombra(draw, linea, x, y, fuente_titulo)
        y += _altura_texto(linea, fuente_titulo) + 8

    y += 14  # separación entre título y tagline

    # 7. Tagline: primera frase del caption (corta y directa)
    x = _centrar_x(primera_frase, fuente_tagline, W)
    _texto_sombra(draw, primera_frase, x, y, fuente_tagline, color=BLANCO_SUAVE)

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
    Monta imagen cuadrada 1080×1080 para feed.

    Layout v4:
      - Foto de fondo a cuadrado completo
      - Gradiente suave inferior
      - Logo circular pequeño arriba-izquierda
      - Título + tagline en zona inferior
      - Sin hashtags en la imagen
    """
    W, H = FEED_W, FEED_H
    logo_path = Path(logo_path) if logo_path else ASSETS_DIR / "logo.png"
    if output_path is None:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        output_path = OUTPUT_DIR / f"{fecha}_{dia_semana}_feed.jpg"
    output_path = Path(output_path)

    base = Image.open(image_path).convert("RGBA")
    base = _escalar_recortar(base, W, H)

    # Gradiente inferior (40%) y superior mínimo (8%)
    _gradiente_vertical(base, int(H * 0.60), H, 0, 155)
    _gradiente_vertical(base, 0, int(H * 0.08), 80, 0)

    draw = ImageDraw.Draw(base)

    # Logo circular
    _logo_circular(base, logo_path, diametro=72, x=28, y=22)

    # Título
    fuente_titulo = _fuente(108, display=True)
    fuente_tagline = _fuente(40)

    titulo_limpio = (titulo or dia_semana.upper()).replace("\n", " ").strip().upper()
    lineas_titulo = textwrap.wrap(titulo_limpio, width=12)[:2]

    y = int(H * 0.62)
    for linea in lineas_titulo:
        x = _centrar_x(linea, fuente_titulo, W)
        _texto_sombra(draw, linea, x, y, fuente_titulo)
        y += _altura_texto(linea, fuente_titulo) + 6

    y += 10

    # Tagline
    primera_frase = caption.split(".")[0].strip()
    if len(primera_frase) > 38:
        primera_frase = primera_frase[:36].rsplit(" ", 1)[0] + "…"
    x = _centrar_x(primera_frase, fuente_tagline, W)
    _texto_sombra(draw, primera_frase, x, y, fuente_tagline, color=BLANCO_SUAVE)

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

    imagen_base = OUTPUT_DIR / "2026-06-11_miercoles_base.png"
    if not imagen_base.exists():
        logger.info("Creando imagen base de prueba...")
        img = Image.new("RGB", (1024, 1024), (20, 10, 30))
        imagen_base.parent.mkdir(parents=True, exist_ok=True)
        img.save(imagen_base)

    rutas = montar_ambos(
        image_path=imagen_base,
        caption="El miércoles es de mojito. Sin discusión. Ven a vernos.",
        hashtags=["#MiercolesDelMojito", "#MerakiBilbao", "#Santutxu"],
        fecha="2026-06-11",
        dia_semana="miercoles",
        titulo="Miércoles de Mojitos",
    )

    for formato, ruta in rutas.items():
        with Image.open(ruta) as img:
            print(f"{formato}: {ruta.name} — {img.size[0]}×{img.size[1]} px — {ruta.stat().st_size // 1024} KB")
