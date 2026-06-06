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

# Prompt base que se usa siempre como contexto visual del bar
PROMPT_BASE = (
    "dark atmospheric cocktail bar, warm amber lighting, moody editorial style, "
    "bokeh background, no text, no people, cinematic, high quality, photorealistic"
)

# Prompt negativo para evitar artefactos comunes
PROMPT_NEGATIVO = (
    "text, watermark, logo, people, faces, blurry, low quality, "
    "cartoon, drawing, anime, oversaturated, nsfw"
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
            with torch.inference_mode():
                resultado = pipe(
                    prompt=prompt,
                    negative_prompt=PROMPT_NEGATIVO,
                    num_inference_steps=num_steps,
                    guidance_scale=0.0,   # SDXL-Turbo funciona sin guidance
                    width=1024,
                    height=1024,
                )
            imagen = resultado.images[0]
            imagen.save(output_path, "PNG")
            logger.info(f"Imagen guardada: {output_path}")

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
