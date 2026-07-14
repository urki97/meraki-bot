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

# Los prompts de imagen y temas se leen de pautas.yaml — así el preview
# prueba siempre la configuración real, sin duplicados que se desincronicen
import yaml

with open(BASE_DIR / "config" / "pautas.yaml", encoding="utf-8") as f:
    _pautas = yaml.safe_load(f)

_fechas_preview = {"miercoles": "2026-06-10", "jueves": "2026-06-11", "viernes": "2026-06-12"}
_extra_preview = {
    "miercoles": {
        "idea_creativa": "El miércoles es de mojito. Sin discusión.",
        "titulo": "Miércoles de Mojitos",
        "cocteles_temporada": ["mojito clásico", "mojito de frutos rojos"],
    },
    "jueves": {
        "idea_creativa": "Jueves de pintxopote en Santutxu. La tradición manda.",
        "titulo": "Pintxopote",
        "cocteles_temporada": ["zurito", "caña"],
    },
    "viernes": {
        "idea_creativa": "Viernes de tortilla. La nuestra no se parece a ninguna otra.",
        "titulo": "Tortilla del Día",
        "cocteles_temporada": [],
    },
}

dias_config = {}
for _dia, _cfg in _pautas["dias"].items():
    if _dia not in _fechas_preview:
        continue
    dias_config[_dia] = {
        "fecha": _fechas_preview[_dia],
        "dia_semana": _dia,
        "tema": _cfg["tema"],
        "enfoque": _cfg["enfoque"],
        "hashtag_variable": _cfg["hashtag_variable"],
        "prompt_imagen_extra": _cfg.get("prompt_imagen_extra", ""),
        "titulo_script": _cfg.get("titulo_script"),
        "titulo_grande": _cfg.get("titulo_grande"),
        "temporada": "Verano",
        "evento_especial": None,
        **_extra_preview[_dia],
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
    titulo_script=dia.get("titulo_script"),
    titulo_grande=dia.get("titulo_grande"),
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
