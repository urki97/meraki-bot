"""Script temporal para generar un preview de la publicación del miércoles."""
import logging
from pathlib import Path

from dotenv import load_dotenv

logging.basicConfig(level=logging.WARNING)
load_dotenv()

BASE_DIR = Path(__file__).parent

dia = {
    "fecha": "2026-06-11",
    "dia_semana": "miercoles",
    "tema": "Miércoles de mojitos",
    "enfoque": "promoción fija — mojitos a precio especial (no mencionar precio ni marca)",
    "idea_creativa": "El miércoles es de mojito. Sin discusión.",
    "titulo": "Miércoles de Mojitos",
    "hashtag_variable": "#MiercolesDelMojito",
    "temporada": "Verano",
    "cocteles_temporada": ["mojito clásico", "mojito de frutos rojos"],
    "evento_especial": None,
}

from agents.copy_agent import generar_caption
print("Generando caption con Ollama...")
resultado = generar_caption(dia, modelo="llama3.1:8b")
print("Caption  :", resultado["caption"])
print("Hashtags :", " ".join(resultado["hashtags"]))

from agents.compositor import montar_ambos
from agents.image_agent import obtener_imagen_base
import os
modelo_sdxl = os.getenv("SDXL_MODEL", "stabilityai/sdxl-turbo")
print("\nGenerando imagen con SDXL-Turbo...")
imagen_base = obtener_imagen_base(dia, modelo=modelo_sdxl, usar_fotos_reales=False)
print(f"Imagen base: {imagen_base}")
print("Montando story...")
rutas = montar_ambos(
    image_path=imagen_base,
    caption=resultado["caption"],
    hashtags=resultado["hashtags"],
    fecha="2026-06-11",
    dia_semana="miercoles",
    titulo="Miércoles\nde Mojitos",
)
print("Story:", rutas["story"])
print("Feed :", rutas["feed"])
