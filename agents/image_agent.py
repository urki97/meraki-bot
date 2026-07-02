"""
Image Agent: genera la imagen base de la story usando SDXL-Turbo.
Gestiona la VRAM cuidadosamente: carga el modelo, genera y lo descarga.
No puede coexistir en VRAM con Ollama — llamar siempre después de Ollama.
"""

import gc
import logging
import os
import time
from pathlib import Path

import torch

logger = logging.getLogger("image_agent")

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "output"

# Prompt base inspirado en el ambiente real del bar Meraki:
# techo de madera, papel tropical de hojas, barra de metal, neón rojo MERAKI,
# plantas, luces cálidas Edison, botellas en estantería
# Prompt base acotado a ~35 tokens para dejar espacio al prompt del día (CLIP max 77).
# Clave anti-"look IA": foto casual de móvil con luz natural, NO editorial/magazine
# (esos términos empujan hacia el acabado pulido artificial típico de SDXL)
PROMPT_BASE = (
    "candid photo taken with a phone inside a small cozy bar, dim warm light, "
    "Edison bulbs, tropical leaf wallpaper, worn metal counter, natural muted colors, "
    "centered subject fully in frame, no text, no people"
)

# Prompt negativo reforzado contra el aspecto de render/CGI y texto inventado
# (los carteles con letras sin sentido son el delator nº1 de imagen generada)
PROMPT_NEGATIVO = (
    "text, words, letters, signs, posters, menu board, labels with writing, "
    "watermark, logo, people, faces, blurry, low quality, cartoon, anime, "
    "3d render, cgi, illustration, painting, plastic, glossy, oversaturated, "
    "studio lighting, product shot, hdr, perfect composition, nsfw"
)


def _liberar_vram() -> None:
    """Libera VRAM y RAM de forma agresiva."""
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.synchronize()
    logger.debug("VRAM liberada")


def _construir_prompt(dia: dict) -> str:
    """Combina el prompt base con el extra del día."""
    extra = dia.get("prompt_imagen_extra", "").strip()
    if extra:
        return f"{PROMPT_BASE}, {extra}"
    return PROMPT_BASE


def _post_procesar_realismo(path: Path, seed: int) -> None:
    """
    Disimula el acabado sintético de SDXL para que parezca foto de móvil:
      - baja la saturación (SDXL satura de más)
      - añade grano fotográfico sutil
      - viñeta muy ligera en las esquinas

    Se sobreescribe el fichero en el sitio.
    """
    import numpy as np
    from PIL import Image, ImageEnhance

    img = Image.open(path).convert("RGB")

    # 1. Saturación y contraste ligeramente rebajados
    img = ImageEnhance.Color(img).enhance(0.88)
    img = ImageEnhance.Contrast(img).enhance(0.97)

    arr = np.asarray(img).astype(np.int16)

    # 2. Grano fotográfico (ruido gaussiano suave, reproducible con la seed)
    rng = np.random.default_rng(seed)
    grano = rng.normal(0, 5, arr.shape).astype(np.int16)
    arr = arr + grano

    # 3. Viñeta sutil: oscurece las esquinas un máximo de ~12%
    h, w = arr.shape[:2]
    ys = (np.linspace(-1, 1, h) ** 2)[:, None]
    xs = (np.linspace(-1, 1, w) ** 2)[None, :]
    vineta = 1.0 - 0.12 * np.clip(ys + xs - 0.4, 0, 1)
    arr = arr * vineta[:, :, None]

    resultado = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    resultado.save(path, "PNG")
    logger.info("Post-procesado de realismo aplicado (grano + saturación + viñeta)")


def foto_real_disponible(dia: dict) -> Path | None:
    """
    Comprueba si hay fotos reales del bar para usar como fondo.
    Busca en assets/fotos_reales/ ficheros que contengan el día de la semana.
    Si hay varias, elige una al azar para variedad.
    Devuelve la ruta o None si no hay ninguna.
    """
    import random
    fotos_dir = BASE_DIR / "assets" / "fotos_reales"
    if not fotos_dir.exists():
        return None

    # Buscar fotos específicas del día primero
    nombre_dia = dia.get("dia_semana", "")
    extensiones = {".jpg", ".jpeg", ".png", ".webp"}

    fotos_dia = [
        f for f in fotos_dir.iterdir()
        if f.suffix.lower() in extensiones and nombre_dia in f.stem.lower()
    ]
    if fotos_dia:
        elegida = random.choice(fotos_dia)
        logger.info(f"Foto real específica para {nombre_dia}: {elegida.name}")
        return elegida

    # Si no hay del día, usar cualquier foto del bar
    fotos_generales = [f for f in fotos_dir.iterdir() if f.suffix.lower() in extensiones]
    if fotos_generales:
        elegida = random.choice(fotos_generales)
        logger.info(f"Foto real general del bar: {elegida.name}")
        return elegida

    return None


def obtener_imagen_base(dia: dict, modelo: str = "stabilityai/sdxl-turbo",
                        usar_fotos_reales: bool = False) -> Path:
    """
    Obtiene la imagen base para el día.
    Por defecto genera siempre con SDXL-Turbo.
    Pasar usar_fotos_reales=True solo cuando se quiera usar una foto manual específica.
    """
    if usar_fotos_reales:
        foto = foto_real_disponible(dia)
        if foto:
            logger.info(f"Usando foto real del bar: {foto}")
            return foto
    logger.info("Generando imagen con SDXL-Turbo...")
    return generar_imagen(dia, modelo=modelo)


def generar_imagen(
    dia: dict,
    modelo: str = "stabilityai/sdxl-turbo",
    output_dir: Path | None = None,
    num_steps: int = 4,
) -> Path:
    """
    Genera la imagen base para el día dado con SDXL-Turbo.

    Flujo de VRAM:
      1. Libera VRAM antes de cargar
      2. Carga SDXL-Turbo en GPU
      3. Genera imagen
      4. Mueve modelo a CPU y libera VRAM

    Args:
        dia: entrada del weekly_plan para un día concreto
        modelo: ID del modelo en HuggingFace
        output_dir: directorio de salida (por defecto output/)
        num_steps: pasos de inferencia (4 es óptimo para SDXL-Turbo)

    Returns:
        Path de la imagen generada (PNG 1080x1080 base, el compositor la ajusta)
    """
    from diffusers import AutoPipelineForText2Image

    if output_dir is None:
        output_dir = OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    # Nombre de fichero basado en la fecha y día
    fecha = dia.get("fecha", "unknown")
    nombre_dia = dia.get("dia_semana", "dia")
    output_path = output_dir / f"{fecha}_{nombre_dia}_base.png"

    # Si ya existe, reutilizar
    if output_path.exists():
        logger.info(f"Imagen base ya existe: {output_path}")
        return output_path

    prompt = _construir_prompt(dia)
    logger.info(f"Generando imagen para {nombre_dia} ({fecha})")
    logger.info(f"Prompt: {prompt[:80]}...")

    # Seed aleatoria en cada generación — así regenerar produce imágenes
    # distintas y la seed queda guardada en el plan por si se quiere repetir
    import random
    seed = random.randint(0, 2**31 - 1)
    dia["seed_imagen"] = seed
    logger.info(f"Seed: {seed}")

    # Liberar VRAM antes de cargar SDXL (Ollama debe haber terminado ya)
    _liberar_vram()

    dispositivo = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info(f"Dispositivo: {dispositivo}")

    ultimo_error = None
    for intento in range(1, 3):
        try:
            logger.info(f"Cargando {modelo} (intento {intento})...")
            pipe = AutoPipelineForText2Image.from_pretrained(
                modelo,
                torch_dtype=torch.float16,
                variant="fp16",
                use_safetensors=True,
            )
            pipe = pipe.to(dispositivo)
            # Optimizaciones de memoria
            pipe.enable_attention_slicing()

            logger.info("Generando imagen...")
            generador = torch.Generator(device=dispositivo).manual_seed(seed)
            with torch.inference_mode():
                resultado = pipe(
                    prompt=prompt,
                    negative_prompt=PROMPT_NEGATIVO,
                    num_inference_steps=num_steps,
                    guidance_scale=0.0,   # SDXL-Turbo funciona sin guidance
                    width=576,
                    height=1024,   # portrait 9:16 — evita crop lateral del sujeto en story
                    generator=generador,
                )
            imagen = resultado.images[0]
            imagen.save(output_path, "PNG")
            logger.info(f"Imagen guardada: {output_path}")

            # Disimular el acabado sintético antes de componer
            _post_procesar_realismo(output_path, seed)

            # Eliminar pipeline y liberar VRAM (fp16 no se mueve a CPU)
            del pipe
            _liberar_vram()

            return output_path

        except torch.cuda.OutOfMemoryError as e:
            ultimo_error = e
            logger.warning(f"OOM en intento {intento}: {e}")
            # Intentar liberar y reintentar una vez
            try:
                del pipe
            except Exception:
                pass
            _liberar_vram()
            if intento < 2:
                logger.info("Esperando 30s antes de reintentar...")
                time.sleep(30)

        except Exception as e:
            ultimo_error = e
            logger.error(f"Error inesperado en intento {intento}: {e}")
            try:
                del pipe
            except Exception:
                pass
            _liberar_vram()
            break

    raise RuntimeError(
        f"No se pudo generar imagen para {nombre_dia} tras 2 intentos: {ultimo_error}"
    )


if __name__ == "__main__":
    import json
    from dotenv import load_dotenv

    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        level=logging.INFO,
    )

    load_dotenv(BASE_DIR / ".env")
    modelo = os.getenv("SDXL_MODEL", "stabilityai/sdxl-turbo")

    # Día de prueba — miércoles de mojitos para tener un prompt concreto
    dia_prueba = {
        "fecha": "2026-06-04",
        "dia_semana": "miercoles",
        "tema": "Miércoles de mojitos",
        "prompt_imagen_extra": "mojito cocktail, mint leaves, lime, crushed ice, backlit, dark bar",
    }

    print(f"\nGenerando imagen para: {dia_prueba['dia_semana'].upper()}")
    print(f"Modelo: {modelo}")
    print(f"CUDA disponible: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        props = torch.cuda.get_device_properties(0)
        vram_gb = props.total_memory / 1024**3
        print(f"GPU: {props.name} — {vram_gb:.1f} GB VRAM\n")

    ruta = generar_imagen(dia_prueba, modelo=modelo)
    print(f"\nImagen generada: {ruta}")
    print(f"Tamaño: {ruta.stat().st_size / 1024:.0f} KB")
