"""
Compositor v6: diseño editorial de coctelería, al estilo de las plantillas
profesionales de hostelería (serif + script, marco fino, ornamentos, footer).

Elementos del layout:
  - Marco fino dorado alrededor de toda la pieza
  - Logo circular centrado arriba
  - Título en dos niveles: línea script manuscrita ("Miércoles de")
    + palabra grande en serif con tracking ("MOJITOS")
  - Ornamento divisor: línea — rombo — línea
  - Tagline corta en el color de acento extraído de la foto
  - Footer con @usuario y barrio en versalitas espaciadas
  - Gradiente adaptativo según el brillo del fondo

Formatos:
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

# Colores
BLANCO       = (255, 255, 255, 255)
BLANCO_SUAVE = (240, 235, 225, 235)
DORADO       = (212, 175, 100, 255)
DORADO_SUAVE = (212, 175, 100, 150)
FOOTER_COLOR = (225, 218, 205, 210)

# Marca (footer)
HANDLE = "@MERAKIBILBAO"
BARRIO = "SANTUTXU · BILBAO"


def _fuente(tamanyo: int, display: bool = False, script: bool = False,
            italic: bool = False) -> ImageFont.FreeTypeFont:
    """Carga la fuente adecuada según el rol."""
    if script:
        # Great Vibes: manuscrita elegante para la línea introductoria
        candidatos = [FONTS_DIR / "GreatVibes-Regular.ttf",
                      FONTS_DIR / "Montserrat-LightItalic.ttf"]
    elif display:
        # Playfair Display: serif de coctelería para la palabra protagonista
        candidatos = [
            FONTS_DIR / "PlayfairDisplay-ExtraBold.ttf",
            FONTS_DIR / "Poppins-Bold.ttf",
            Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
        ]
    elif italic:
        candidatos = [
            FONTS_DIR / "Montserrat-LightItalic.ttf",
            Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
        ]
    else:
        candidatos = [
            FONTS_DIR / "Poppins-SemiBold.ttf",
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


def _analizar_fondo(img: Image.Image, y0: int, y1: int) -> tuple[float, tuple]:
    """
    Analiza la zona donde irá el texto.
    Devuelve (brillo 0-1, color_acento pastel extraído de la foto).
    """
    import numpy as np

    zona = img.crop((0, y0, img.width, y1)).convert("RGB").resize((64, 32))
    arr = np.asarray(zona).astype(float)
    brillo = float(arr.mean() / 255.0)

    mx = arr.max(axis=2)
    mn = arr.min(axis=2)
    sat = (mx - mn) / (mx + 1e-5)
    vivos = (sat > 0.35) & (mx > 70)
    if vivos.sum() >= 20:
        acento = arr[vivos].mean(axis=0)
    else:
        acento = np.array([212.0, 175.0, 100.0])   # dorado Meraki

    acento = acento / max(float(acento.max()), 1.0) * 255.0
    acento = 0.5 * acento + 0.5 * 255.0
    return brillo, tuple(int(c) for c in acento)


def _gradiente_vertical(canvas: Image.Image, y0: int, y1: int,
                         alpha_inicio: int, alpha_fin: int,
                         color_rgb: tuple = (0, 0, 0)) -> None:
    """Gradiente vertical — la foto se ve a través."""
    h = y1 - y0
    for i in range(h):
        t = i / max(h - 1, 1)
        alpha = int(alpha_inicio + (alpha_fin - alpha_inicio) * t)
        franja = Image.new("RGBA", (canvas.width, 1), (*color_rgb, alpha))
        canvas.paste(franja, (0, y0 + i), franja)


def _marco(canvas: Image.Image, inset: int = 28, color=DORADO_SUAVE, grosor: int = 2) -> None:
    """Marco fino elegante alrededor de toda la pieza."""
    draw = ImageDraw.Draw(canvas)
    w, h = canvas.size
    draw.rectangle([inset, inset, w - inset, h - inset], outline=color, width=grosor)


def _logo_circular(canvas: Image.Image, logo_path: Path, diametro: int, x: int, y: int) -> None:
    """Logo recortado en círculo con fondo semitransparente."""
    if not logo_path.exists():
        logger.warning(f"Logo no encontrado: {logo_path}")
        return
    logo = Image.open(logo_path).convert("RGBA")
    logo = logo.resize((diametro, diametro), Image.LANCZOS)

    fondo = Image.new("RGBA", (diametro, diametro), (0, 0, 0, 0))
    mascara = Image.new("L", (diametro, diametro), 0)
    ImageDraw.Draw(mascara).ellipse([0, 0, diametro - 1, diametro - 1], fill=255)
    fondo.paste(logo, (0, 0), logo)
    fondo.putalpha(mascara)
    canvas.paste(fondo, (x, y), fondo)


def _texto_sombra(draw: ImageDraw.Draw, texto: str, x: int, y: int,
                   fuente, color=BLANCO) -> None:
    """Texto con sombra difusa para legibilidad sobre foto."""
    for dx, dy in [(2, 2), (3, 3), (-1, 2), (2, -1)]:
        draw.text((x + dx, y + dy), texto, font=fuente, fill=(0, 0, 0, 120))
    draw.text((x, y), texto, font=fuente, fill=color)


def _ancho_texto(draw: ImageDraw.Draw, texto: str, fuente, tracking: int = 0) -> float:
    """Ancho total del texto incluyendo tracking entre caracteres."""
    return draw.textlength(texto, font=fuente) + tracking * max(len(texto) - 1, 0)


def _texto_espaciado(draw: ImageDraw.Draw, texto: str, y: int, fuente,
                      ancho_max: int, tracking: int = 0, color=BLANCO,
                      sombra: bool = True) -> None:
    """Texto centrado con espaciado entre caracteres (tracking)."""
    total = _ancho_texto(draw, texto, fuente, tracking)
    x = (ancho_max - total) / 2
    for ch in texto:
        if sombra:
            for dx, dy in [(2, 2), (3, 3)]:
                draw.text((x + dx, y + dy), ch, font=fuente, fill=(0, 0, 0, 130))
        draw.text((x, y), ch, font=fuente, fill=color)
        x += draw.textlength(ch, font=fuente) + tracking


def _fuente_ajustada(draw: ImageDraw.Draw, texto: str, ancho_max: int,
                      tamanyo_max: int, tracking: int = 0,
                      display: bool = True) -> ImageFont.FreeTypeFont:
    """Devuelve la fuente display más grande que quepa en ancho_max."""
    tamanyo = tamanyo_max
    while tamanyo > 40:
        fuente = _fuente(tamanyo, display=display)
        if _ancho_texto(draw, texto, fuente, tracking) <= ancho_max:
            return fuente
        tamanyo -= 6
    return _fuente(40, display=display)


def _ornamento(canvas: Image.Image, y: int, ancho: int, largo: int = 130) -> None:
    """Divisor decorativo: línea — rombo — línea, en dorado."""
    draw = ImageDraw.Draw(canvas)
    cx = ancho // 2
    r = 7   # medio lado del rombo
    hueco = 18
    draw.line([(cx - hueco - largo, y), (cx - hueco, y)], fill=DORADO, width=2)
    draw.line([(cx + hueco, y), (cx + hueco + largo, y)], fill=DORADO, width=2)
    draw.polygon([(cx, y - r), (cx + r, y), (cx, y + r), (cx - r, y)], outline=DORADO, width=2)


def _altura_texto(texto: str, fuente) -> int:
    bbox = fuente.getbbox(texto)
    return bbox[3] - bbox[1]


def _titulo_partes(titulo: str | None, titulo_script: str | None,
                    titulo_grande: str | None, dia_semana: str) -> tuple[str, str]:
    """
    Devuelve (linea_script, palabra_grande).
    Si vienen explícitos de pautas.yaml se usan tal cual; si no, se derivan
    del título: última palabra en grande, el resto en script.
    """
    if titulo_grande:
        return titulo_script or "", titulo_grande.upper()

    titulo = (titulo or dia_semana.capitalize()).replace("\n", " ").strip()
    palabras = titulo.split()
    if len(palabras) >= 2:
        return " ".join(palabras[:-1]), palabras[-1].upper()
    return f"{dia_semana.capitalize()} de", titulo.upper()


# ── Story 1080×1920 ───────────────────────────────────────────────────────────

def montar_story(
    image_path: Path | str,
    caption: str,
    hashtags: list[str],
    fecha: str,
    dia_semana: str,
    titulo: str | None = None,
    titulo_script: str | None = None,
    titulo_grande: str | None = None,
    subtitulo: str | None = None,
    logo_path: Path | str | None = None,
    output_path: Path | str | None = None,
) -> Path:
    """
    Monta la story 1080×1920 con el diseño editorial v6.
    """
    W, H = STORY_W, STORY_H
    logo_path = Path(logo_path) if logo_path else ASSETS_DIR / "logo.png"
    if output_path is None:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        output_path = OUTPUT_DIR / f"{fecha}_{dia_semana}_story.jpg"
    output_path = Path(output_path)

    # 1. Foto de fondo
    base = Image.open(image_path).convert("RGBA")
    base = _escalar_recortar(base, W, H)

    # 2. Gradiente adaptativo + acento de color de la foto
    grad_inicio = int(H * 0.56)
    brillo, color_acento = _analizar_fondo(base, grad_inicio, H)
    _gradiente_vertical(base, grad_inicio, H, 0, int(165 + brillo * 60))
    _gradiente_vertical(base, 0, int(H * 0.14), 110, 0)

    # 3. Marco fino dorado
    _marco(base, inset=30)

    draw = ImageDraw.Draw(base)

    # 4. Logo circular centrado arriba
    d_logo = 116
    _logo_circular(base, logo_path, diametro=d_logo, x=(W - d_logo) // 2, y=64)

    # 5. Título en dos niveles
    linea_script, palabra_grande = _titulo_partes(titulo, titulo_script, titulo_grande, dia_semana)

    y = int(H * 0.585)

    # 5a. Línea script manuscrita en el color de acento
    if linea_script:
        fuente_script = _fuente(112, script=True)
        ancho_script = _ancho_texto(draw, linea_script, fuente_script)
        _texto_sombra(draw, linea_script, int((W - ancho_script) / 2), y,
                      fuente_script, color=(*color_acento, 255))
        y += 150

    # 5b. Palabra protagonista en serif, ajustada al ancho, con tracking
    tracking = 6
    fuente_grande = _fuente_ajustada(draw, palabra_grande, W - 150, 165, tracking)
    _texto_espaciado(draw, palabra_grande, y, fuente_grande, W,
                     tracking=tracking, color=BLANCO)
    y += _altura_texto(palabra_grande, fuente_grande) + 46

    # 6. Ornamento divisor
    _ornamento(base, y, W)
    y += 36

    # 7. Tagline (primera frase del caption) en máx 2 líneas
    draw = ImageDraw.Draw(base)   # re-crear tras pegar el ornamento
    primera_frase = caption.split(".")[0].strip()
    fuente_tagline = _fuente(44)
    for linea in textwrap.wrap(primera_frase, width=38)[:2]:
        ancho_l = _ancho_texto(draw, linea, fuente_tagline)
        _texto_sombra(draw, linea, int((W - ancho_l) / 2), y,
                      fuente_tagline, color=BLANCO_SUAVE)
        y += _altura_texto(linea, fuente_tagline) + 14

    # 8. Footer de marca en versalitas espaciadas — siempre bajo la tagline
    fuente_footer = _fuente(27)
    y_footer = max(H - 285, y + 40)
    _texto_espaciado(draw, f"{HANDLE}   ·   {BARRIO}", y_footer, fuente_footer, W,
                     tracking=4, color=FOOTER_COLOR)

    # 9. Guardar
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
    titulo_script: str | None = None,
    titulo_grande: str | None = None,
    logo_path: Path | str | None = None,
    output_path: Path | str | None = None,
) -> Path:
    """
    Monta el cuadrado 1080×1080 con el mismo lenguaje visual que la story.
    """
    W, H = FEED_W, FEED_H
    logo_path = Path(logo_path) if logo_path else ASSETS_DIR / "logo.png"
    if output_path is None:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        output_path = OUTPUT_DIR / f"{fecha}_{dia_semana}_feed.jpg"
    output_path = Path(output_path)

    base = Image.open(image_path).convert("RGBA")
    base = _escalar_recortar(base, W, H)

    grad_inicio = int(H * 0.52)
    brillo, color_acento = _analizar_fondo(base, grad_inicio, H)
    _gradiente_vertical(base, grad_inicio, H, 0, int(160 + brillo * 60))
    _gradiente_vertical(base, 0, int(H * 0.12), 95, 0)

    _marco(base, inset=24)

    draw = ImageDraw.Draw(base)

    d_logo = 88
    _logo_circular(base, logo_path, diametro=d_logo, x=(W - d_logo) // 2, y=44)

    linea_script, palabra_grande = _titulo_partes(titulo, titulo_script, titulo_grande, dia_semana)

    y = int(H * 0.565)

    if linea_script:
        fuente_script = _fuente(80, script=True)
        ancho_script = _ancho_texto(draw, linea_script, fuente_script)
        _texto_sombra(draw, linea_script, int((W - ancho_script) / 2), y,
                      fuente_script, color=(*color_acento, 255))
        y += 104

    tracking = 4
    fuente_grande = _fuente_ajustada(draw, palabra_grande, W - 130, 118, tracking)
    _texto_espaciado(draw, palabra_grande, y, fuente_grande, W,
                     tracking=tracking, color=BLANCO)
    y += _altura_texto(palabra_grande, fuente_grande) + 34

    _ornamento(base, y, W, largo=100)
    y += 26

    draw = ImageDraw.Draw(base)
    primera_frase = caption.split(".")[0].strip()
    fuente_tagline = _fuente(36)
    for linea in textwrap.wrap(primera_frase, width=42)[:2]:
        ancho_l = _ancho_texto(draw, linea, fuente_tagline)
        _texto_sombra(draw, linea, int((W - ancho_l) / 2), y,
                      fuente_tagline, color=BLANCO_SUAVE)
        y += _altura_texto(linea, fuente_tagline) + 12

    fuente_footer = _fuente(23)
    y_footer = max(H - 70, y + 28)
    _texto_espaciado(draw, f"{HANDLE}   ·   {BARRIO}", y_footer, fuente_footer, W,
                     tracking=3, color=FOOTER_COLOR)

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
    titulo_script: str | None = None,
    titulo_grande: str | None = None,
    logo_path: Path | str | None = None,
) -> dict[str, Path]:
    """
    Genera story (1080×1920) y feed (1080×1080) en una sola llamada.
    Devuelve {'story': Path, 'feed': Path}.
    """
    story = montar_story(image_path, caption, hashtags, fecha, dia_semana,
                         titulo=titulo, titulo_script=titulo_script,
                         titulo_grande=titulo_grande, logo_path=logo_path)
    feed  = montar_feed(image_path, caption, hashtags, fecha, dia_semana,
                        titulo=titulo, titulo_script=titulo_script,
                        titulo_grande=titulo_grande, logo_path=logo_path)
    return {"story": story, "feed": feed}


if __name__ == "__main__":
    import os
    from dotenv import load_dotenv

    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        level=logging.INFO,
    )
    load_dotenv(BASE_DIR / ".env")

    imagen_base = OUTPUT_DIR / "2026-06-10_miercoles_base.png"
    if not imagen_base.exists():
        logger.info("Creando imagen base de prueba...")
        img = Image.new("RGB", (576, 1024), (20, 10, 30))
        imagen_base.parent.mkdir(parents=True, exist_ok=True)
        img.save(imagen_base)

    rutas = montar_ambos(
        image_path=imagen_base,
        caption="Con M de Meraki. Con M de Mojito.",
        hashtags=["#MiercolesDelMojito", "#MerakiBilbao", "#Santutxu"],
        fecha="2026-06-10",
        dia_semana="miercoles",
        titulo_script="Miércoles de",
        titulo_grande="Mojitos",
    )

    for formato, ruta in rutas.items():
        with Image.open(ruta) as img:
            print(f"{formato}: {ruta.name} — {img.size[0]}×{img.size[1]} px — {ruta.stat().st_size // 1024} KB")
