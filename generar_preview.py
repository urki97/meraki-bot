"""Script temporal para generar previews de publicaciones."""
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

logging.basicConfig(level=logging.WARNING)
load_dotenv()

BASE_DIR = Path(__file__).parent

# Día a previsualizar: "miercoles", "jueves" o "viernes"
DIA = sys.argv[1] if len(sys.argv) > 1 else "jueves"

dias_config = {
    "miercoles": {
        "fecha": "2026-06-10",
        "dia_semana": "miercoles",
        "tema": "Miércoles de mojitos",
        "enfoque": "promoción fija — mojitos a precio especial (no mencionar precio ni marca)",
        "idea_creativa": "El miércoles es de mojito. Sin discusión.",
        "titulo": "Miércoles de Mojitos",
        "hashtag_variable": "#MiercolesDelMojito",
        "temporada": "Verano",
        "cocteles_temporada": ["mojito clásico", "mojito de frutos rojos"],
        "evento_especial": None,
        "prompt_imagen_extra": (
            "mojito cocktail hero shot, tall glass with crushed ice, fresh mint, lime wedge, "
            "striped straw, condensation, bokeh bar background, magazine quality"
        ),
    },
    "jueves": {
        "fecha": "2026-06-11",
        "dia_semana": "jueves",
        "tema": "pintxopote",
        "enfoque": "pintxo + zurito a precio especial — tradición vasca",
        "idea_creativa": "Jueves de pintxopote en Santutxu. La tradición manda.",
        "titulo": "Pintxopote",
        "hashtag_variable": "#Pintxopote",
        "temporada": "Verano",
        "cocteles_temporada": ["zurito", "caña"],
        "evento_especial": None,
        "prompt_imagen_extra": (
            "basque pintxos on metal bar counter, mini sandwiches, small beer glass, "
            "warm bar light, red neon bokeh, close-up food photography, appetizing"
        ),
    },
    "viernes": {
        "fecha": "2026-06-12",
        "dia_semana": "viernes",
        "tema": "tortillas especiales",
        "enfoque": "tortillas especiales del día — plato estrella del viernes",
        "idea_creativa": "Viernes de tortilla. La nuestra no se parece a ninguna otra.",
        "titulo": "Tortilla del Día",
        "hashtag_variable": "#TortillaDelDia",
        "temporada": "Verano",
        "cocteles_temporada": [],
        "evento_especial": None,
        "prompt_imagen_extra": (
            "golden spanish tortilla omelette slice on slate plate, herbs garnish, "
            "metal bar counter, warm Edison glow, red neon bokeh, close-up food photography"
        ),
    },
}

# Captions fijos de referencia por día (estilo aprobado por el bar)
captions_referencia = {
    "miercoles": "Con M de Meraki. Con M de Mojito.",
    "jueves":    "Ven a disfrutar de nuestra riquísima variedad de pintxos.",
    "viernes":   "La tortilla del viernes te espera desde el lunes.",
}

dia = dias_config[DIA]
print(f"\n=== Generando preview para {DIA.upper()} ===\n")

# Si el día tiene caption de referencia, usarlo directamente; si no, generar con Ollama
if DIA in captions_referencia:
    caption_texto = captions_referencia[DIA]
    hashtags_dia = {
        "miercoles": ["#MiercolesDelMojito", "#MerakiBilbao", "#Santutxu"],
        "jueves":    ["#Pintxopote", "#MerakiBilbao", "#Santutxu"],
        "viernes":   ["#TortillaDelDia", "#MerakiBilbao", "#Santutxu"],
    }[DIA]
    resultado = {"caption": caption_texto, "hashtags": hashtags_dia}
    print("Caption  :", resultado["caption"])
    print("Hashtags :", " ".join(resultado["hashtags"]))
else:
    from agents.copy_agent import generar_caption
    print("Generando caption con Ollama...")
    resultado = generar_caption(dia, modelo="llama3.1:8b")
    print("Caption  :", resultado["caption"])
    print("Hashtags :", " ".join(resultado["hashtags"]))

from agents.compositor import montar_ambos
from agents.image_agent import obtener_imagen_base

modelo_sdxl = os.getenv("SDXL_MODEL", "stabilityai/sdxl-turbo")
print(f"\nGenerando imagen con SDXL-Turbo ({modelo_sdxl})...")
imagen_base = obtener_imagen_base(dia, modelo=modelo_sdxl, usar_fotos_reales=False)
print(f"Imagen base: {imagen_base}")

print("Montando story y feed...")
rutas = montar_ambos(
    image_path=imagen_base,
    caption=resultado["caption"],
    hashtags=resultado["hashtags"],
    fecha=dia["fecha"],
    dia_semana=DIA,
    titulo=dia["titulo"],
)
print("Story:", rutas["story"])
print("Feed :", rutas["feed"])

# Copiar a escritorio Windows
escritorio = Path("/mnt/c/Users/URKI/Desktop")
if escritorio.exists():
    import shutil
    shutil.copy(rutas["story"], escritorio / f"meraki_preview_{DIA}_story.jpg")
    shutil.copy(rutas["feed"],  escritorio / f"meraki_preview_{DIA}_feed.jpg")
    print(f"\nCopiado al escritorio: meraki_preview_{DIA}_story.jpg + _feed.jpg")
