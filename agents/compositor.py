"""
Compositor: monta la story final 1080x1920 combinando:
  - Imagen base (de SDXL-Turbo o foto real del bar)
  - Overlay oscuro semitransparente para legibilidad
  - Caption centrado en el tercio inferior
  - Logo Meraki en la esquina inferior centrado

Acepta image_path opcional para usar fotos reales del bar
en lugar de la imagen generada por IA.
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

# Dimensiones de la story Instagram
STORY_W = 1080
STORY_H = 1920

# Overlay oscuro sobre la imagen base
OVERLAY_ALPHA = int(255 * 0.45)  # 45% opacidad

# Colores
COLOR_TEXTO = (255, 255, 255, 255)        # blanco puro
COLOR_TEXTO_SOMBRA = (0, 0, 0, 180)      # sombra semitransparente
COLOR_LINEA_DECORATIVA = (195, 155, 70, 200)  # dorado Meraki


def _obtener_fuente(tamanyo: int, negrita: bool = False) -> ImageFont.FreeTypeFont:
    """
    Carga una fuente del sistema. Busca en orden:
    1. Fonts del proyecto (assets/fonts/)
    2. Fuentes del sistema Ubuntu
    3. Fuente por defecto de Pillow como último recurso
    """
    candidatos_negrita = [
        FONTS_DIR / "Inter-Bold.ttf",
        FONTS_DIR / "Roboto-Bold.ttf",
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
        Path("/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf"),
    ]
    candidatos_normal = [
        FONTS_DIR / "Inter-Regular.ttf",
        FONTS_DIR / "Roboto-Regular.ttf",
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
        Path("/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf"),
    ]
    candidatos = candidatos_negrita if negrita else candidatos_normal

    for ruta in candidatos:
        if ruta.exists():
            try:
                return ImageFont.truetype(str(ruta), tamanyo)
            except Exception:
                continue

    logger.warning(f"No se encontró fuente TTF, usando fuente por defecto a tamaño {tamanyo}")
    return ImageFont.load_default(size=tamanyo)


def _escalar_imagen_base(img: Image.Image) -> Image.Image:
    """Escala y recorta la imagen base para que llene 1080x1920."""
    ratio_story = STORY_W / STORY_H
    ratio_img = img.width / img.height

    if ratio_img > ratio_story:
        # Imagen más ancha: ajustar por altura
        nuevo_alto = STORY_H
        nuevo_ancho = int(img.width * STORY_H / img.height)
    else:
        # Imagen más alta: ajustar por ancho
        nuevo_ancho = STORY_W
        nuevo_alto = int(img.height * STORY_W / img.width)

    img = img.resize((nuevo_ancho, nuevo_alto), Image.LANCZOS)

    # Recorte centrado
    left = (nuevo_ancho - STORY_W) // 2
    top = (nuevo_alto - STORY_H) // 2
    return img.crop((left, top, left + STORY_W, top + STORY_H))


def _aplicar_overlay(base: Image.Image) -> Image.Image:
    """Aplica overlay oscuro semitransparente para mejorar legibilidad del texto."""
    overlay = Image.new("RGBA", (STORY_W, STORY_H), (0, 0, 0, OVERLAY_ALPHA))
    resultado = base.copy().convert("RGBA")
    resultado = Image.alpha_composite(resultado, overlay)
    return resultado


def _dibujar_texto_con_sombra(
    draw: ImageDraw.Draw,
    texto: str,
    pos: tuple[int, int],
    fuente: ImageFont.FreeTypeFont,
    color: tuple = COLOR_TEXTO,
    offset_sombra: int = 3,
) -> None:
    """Dibuja texto con sombra para mejor legibilidad sobre imágenes."""
    x, y = pos
    # Sombra
    draw.text((x + offset_sombra, y + offset_sombra), texto, font=fuente, fill=COLOR_TEXTO_SOMBRA)
    # Texto principal
    draw.text((x, y), texto, font=fuente, fill=color)


def _calcular_alto_texto(lineas: list[str], fuente: ImageFont.FreeTypeFont, espaciado: int) -> int:
    """Calcula la altura total del bloque de texto."""
    alto_total = 0
    for linea in lineas:
        bbox = fuente.getbbox(linea)
        alto_total += (bbox[3] - bbox[1]) + espaciado
    return alto_total


def montar_story(
    image_path: Path | str,
    caption: str,
    hashtags: list[str],
    fecha: str,
    dia_semana: str,
    logo_path: Path | str | None = None,
    output_path: Path | str | None = None,
) -> Path:
    """
    Monta la story final 1080x1920.

    Args:
        image_path: ruta a la imagen base (SDXL o foto real del bar)
        caption: texto del post
        hashtags: lista de hashtags
        fecha: fecha del post (YYYY-MM-DD)
        dia_semana: nombre del día (para el nombre del fichero de salida)
        logo_path: ruta al logo (por defecto assets/logo.png)
        output_path: ruta de salida (por defecto output/{fecha}_{dia}_story.png)

    Returns:
        Path de la story generada
    """
    if logo_path is None:
        logo_path = ASSETS_DIR / "logo.png"
    if output_path is None:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        output_path = OUTPUT_DIR / f"{fecha}_{dia_semana}_story.png"

    output_path = Path(output_path)
    image_path = Path(image_path)

    logger.info(f"Montando story para {dia_semana} ({fecha})...")

    # ── 1. Cargar y preparar imagen base ─────────────────────────────────────
    base = Image.open(image_path).convert("RGB")
    base = _escalar_imagen_base(base)

    # ── 2. Aplicar overlay oscuro ─────────────────────────────────────────────
    canvas = _aplicar_overlay(base)
    draw = ImageDraw.Draw(canvas)

    # ── 3. Línea decorativa dorada superior ──────────────────────────────────
    margen = 60
    draw.line(
        [(margen, 100), (STORY_W - margen, 100)],
        fill=COLOR_LINEA_DECORATIVA,
        width=2,
    )

    # ── 4. Nombre del bar en la parte superior ────────────────────────────────
    fuente_nombre = _obtener_fuente(38, negrita=True)
    nombre_bar = "MERAKI BAR & COCKTAILS"
    bbox = fuente_nombre.getbbox(nombre_bar)
    ancho_nombre = bbox[2] - bbox[0]
    x_nombre = (STORY_W - ancho_nombre) // 2
    _dibujar_texto_con_sombra(draw, nombre_bar, (x_nombre, 120), fuente_nombre, COLOR_LINEA_DECORATIVA)

    # ── 5. Línea decorativa dorada debajo del nombre ──────────────────────────
    draw.line(
        [(margen, 175), (STORY_W - margen, 175)],
        fill=COLOR_LINEA_DECORATIVA,
        width=1,
    )

    # ── 6. Caption en el tercio inferior ─────────────────────────────────────
    fuente_caption = _obtener_fuente(52, negrita=False)
    fuente_hashtags = _obtener_fuente(38, negrita=False)

    # Ajustar caption a múltiples líneas (máx ~22 chars por línea)
    lineas_caption = textwrap.wrap(caption, width=22)
    espaciado_lineas = 18

    alto_caption = _calcular_alto_texto(lineas_caption, fuente_caption, espaciado_lineas)
    alto_hashtags = 55  # una línea de hashtags

    # Zona de texto: desde el 58% de la altura hasta el 88%
    zona_texto_top = int(STORY_H * 0.58)
    zona_texto_bottom = int(STORY_H * 0.88)
    zona_alto = zona_texto_bottom - zona_texto_top

    # Centrar verticalmente el bloque de texto en la zona
    y_actual = zona_texto_top + (zona_alto - alto_caption - alto_hashtags - 30) // 2

    for linea in lineas_caption:
        bbox = fuente_caption.getbbox(linea)
        ancho_linea = bbox[2] - bbox[0]
        x_linea = (STORY_W - ancho_linea) // 2
        _dibujar_texto_con_sombra(draw, linea, (x_linea, y_actual), fuente_caption)
        alto_linea = bbox[3] - bbox[1]
        y_actual += alto_linea + espaciado_lineas

    # Hashtags
    texto_hashtags = " ".join(hashtags)
    y_actual += 15
    bbox = fuente_hashtags.getbbox(texto_hashtags)
    ancho_hashtags = bbox[2] - bbox[0]
    x_hashtags = (STORY_W - ancho_hashtags) // 2
    _dibujar_texto_con_sombra(
        draw, texto_hashtags, (x_hashtags, y_actual),
        fuente_hashtags, color=(180, 180, 180, 255)
    )

    # ── 7. Logo en la parte inferior centrado ─────────────────────────────────
    logo_path = Path(logo_path)
    if logo_path.exists():
        logo = Image.open(logo_path).convert("RGBA")
        # Escalar logo a 160px de ancho manteniendo proporción
        logo_ancho = 160
        logo_alto = int(logo.height * logo_ancho / logo.width)
        logo = logo.resize((logo_ancho, logo_alto), Image.LANCZOS)

        # Posición: centrado horizontalmente, 60px del borde inferior
        x_logo = (STORY_W - logo_ancho) // 2
        y_logo = STORY_H - logo_alto - 60

        # Pegar con transparencia
        canvas.paste(logo, (x_logo, y_logo), logo)
    else:
        logger.warning(f"Logo no encontrado en {logo_path}")

    # ── 8. Guardar ────────────────────────────────────────────────────────────
    canvas_rgb = canvas.convert("RGB")
    canvas_rgb.save(output_path, "JPEG", quality=92, optimize=True)
    logger.info(f"Story guardada: {output_path} ({output_path.stat().st_size // 1024} KB)")

    return output_path


if __name__ == "__main__":
    import os
    from dotenv import load_dotenv

    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        level=logging.INFO,
    )

    load_dotenv(BASE_DIR / ".env")

    # Buscar imagen base generada por el image_agent
    imagen_base = OUTPUT_DIR / "2026-06-04_miercoles_base.png"
    if not imagen_base.exists():
        # Crear imagen de prueba si no existe
        logger.info("Creando imagen base de prueba (800x800 oscura)...")
        img_prueba = Image.new("RGB", (800, 800), (15, 15, 25))
        draw_prueba = ImageDraw.Draw(img_prueba)
        draw_prueba.ellipse([200, 200, 600, 600], fill=(40, 25, 10))
        imagen_base.parent.mkdir(parents=True, exist_ok=True)
        img_prueba.save(imagen_base)

    caption_prueba = "El miércoles es de mojito. Sin discusión. Ven a Meraki."
    hashtags_prueba = ["#MiercolesDelMojito", "#MerakiBilbao", "#Santutxu"]

    story_path = montar_story(
        image_path=imagen_base,
        caption=caption_prueba,
        hashtags=hashtags_prueba,
        fecha="2026-06-04",
        dia_semana="miercoles",
    )

    print(f"\nStory generada: {story_path}")
    print(f"Tamaño: {story_path.stat().st_size // 1024} KB")

    # Verificar dimensiones
    with Image.open(story_path) as img:
        print(f"Dimensiones: {img.size[0]}x{img.size[1]} px")
        print("✓ Story montada correctamente" if img.size == (STORY_W, STORY_H) else "✗ Dimensiones incorrectas")
