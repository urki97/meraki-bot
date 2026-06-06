"""
Test end-to-end del pipeline completo sin publicar.
Ejecuta: planner → copy → imagen → compositor → publisher (DRY_RUN).
No requiere credenciales de Telegram ni Meta.
"""

import json
import logging
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Asegurar que el root del proyecto está en el path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault("DRY_RUN", "true")

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("test_pipeline")


class TestConfigYaml(unittest.TestCase):
    """Verifica que los ficheros de configuración son válidos y completos."""

    def test_pautas_yaml_cargable(self):
        import yaml
        ruta = BASE_DIR / "config" / "pautas.yaml"
        self.assertTrue(ruta.exists(), "pautas.yaml no existe")
        with open(ruta) as f:
            datos = yaml.safe_load(f)
        self.assertIn("bar", datos)
        self.assertIn("dias", datos)
        self.assertIn("hashtags", datos)

    def test_todos_los_dias_configurados(self):
        import yaml
        with open(BASE_DIR / "config" / "pautas.yaml") as f:
            datos = yaml.safe_load(f)
        dias_esperados = {"lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"}
        dias_config = set(datos["dias"].keys())
        self.assertEqual(dias_esperados, dias_config, f"Días faltantes: {dias_esperados - dias_config}")

    def test_calendar_yaml_cargable(self):
        import yaml
        ruta = BASE_DIR / "config" / "calendar.yaml"
        self.assertTrue(ruta.exists(), "calendar.yaml no existe")
        with open(ruta) as f:
            datos = yaml.safe_load(f)
        self.assertIn("recurrentes", datos)
        self.assertIn("especiales", datos)
        self.assertIn("temporadas", datos)


class TestPlanner(unittest.TestCase):
    """Verifica que el planner genera un plan correcto (mockeando Ollama)."""

    def setUp(self):
        # Limpiar plan existente para forzar regeneración
        state_file = BASE_DIR / "state" / "weekly_plan.json"
        if state_file.exists():
            state_file.unlink()

    def test_genera_plan_7_dias(self):
        """El planner debe generar exactamente 7 entradas, una por día."""
        # Mockear la llamada a Ollama para no depender del servicio
        with patch("ollama.generate") as mock_ollama:
            mock_ollama.return_value = {"response": "Idea de prueba para el test."}
            from agents.planner import generar_plan_semanal
            plan = generar_plan_semanal(forzar=True)

        self.assertEqual(len(plan), 7, f"Se esperaban 7 días, se obtuvieron {len(plan)}")

    def test_estructura_de_cada_dia(self):
        """Cada día del plan debe tener los campos obligatorios."""
        campos_requeridos = {
            "fecha", "dia_semana", "tema", "enfoque",
            "idea_creativa", "hashtag_variable", "estado",
            "intentos_regeneracion",
        }
        with patch("ollama.generate") as mock_ollama:
            mock_ollama.return_value = {"response": "Idea de prueba."}
            from agents.planner import generar_plan_semanal
            plan = generar_plan_semanal(forzar=True)

        for fecha, dia in plan.items():
            faltantes = campos_requeridos - set(dia.keys())
            self.assertFalse(faltantes, f"{fecha}: campos faltantes {faltantes}")

    def test_estados_iniciales_pendiente(self):
        """Todos los días deben empezar en estado 'pendiente'."""
        with patch("ollama.generate") as mock_ollama:
            mock_ollama.return_value = {"response": "Idea de prueba."}
            from agents.planner import generar_plan_semanal
            plan = generar_plan_semanal(forzar=True)

        for fecha, dia in plan.items():
            self.assertEqual(dia["estado"], "pendiente", f"{fecha} no está en estado pendiente")

    def test_plan_se_persiste_en_disco(self):
        """El plan generado debe persistirse en state/weekly_plan.json."""
        with patch("ollama.generate") as mock_ollama:
            mock_ollama.return_value = {"response": "Idea."}
            from agents.planner import generar_plan_semanal
            generar_plan_semanal(forzar=True)

        state_file = BASE_DIR / "state" / "weekly_plan.json"
        self.assertTrue(state_file.exists(), "weekly_plan.json no fue creado")
        with open(state_file) as f:
            plan = json.load(f)
        self.assertEqual(len(plan), 7)


class TestCopyAgent(unittest.TestCase):
    """Verifica que el copy agent genera caption y hashtags válidos."""

    DIA_PRUEBA = {
        "fecha": "2026-06-04",
        "dia_semana": "miercoles",
        "tema": "Miércoles de mojitos",
        "enfoque": "mojitos a precio especial",
        "idea_creativa": "El miércoles es de mojito. Sin discusión.",
        "hashtag_variable": "#MiercolesDelMojito",
        "temporada": "Verano",
        "cocteles_temporada": ["mojito clásico"],
        "evento_especial": None,
    }

    def test_genera_caption_y_hashtags(self):
        """El copy agent debe devolver caption y hashtags no vacíos."""
        respuesta_mock = json.dumps({
            "caption": "El miércoles es de mojito. Sin discusión. Ven a Meraki.",
            "hashtags": ["#MiercolesDelMojito", "#MerakiBilbao", "#Santutxu"],
        })
        with patch("ollama.generate") as mock_ollama:
            mock_ollama.return_value = {"response": respuesta_mock}
            from agents.copy_agent import generar_caption
            resultado = generar_caption(self.DIA_PRUEBA)

        self.assertIn("caption", resultado)
        self.assertIn("hashtags", resultado)
        self.assertTrue(len(resultado["caption"]) > 0)
        self.assertTrue(len(resultado["hashtags"]) > 0)

    def test_hashtags_fijos_incluidos(self):
        """Los hashtags fijos #MerakiBilbao y #Santutxu deben estar siempre."""
        respuesta_mock = json.dumps({
            "caption": "Test caption.",
            "hashtags": ["#MiercolesDelMojito"],
        })
        with patch("ollama.generate") as mock_ollama:
            mock_ollama.return_value = {"response": respuesta_mock}
            from agents.copy_agent import generar_caption
            resultado = generar_caption(self.DIA_PRUEBA)

        self.assertIn("#MerakiBilbao", resultado["hashtags"])
        self.assertIn("#Santutxu", resultado["hashtags"])

    def test_maximo_3_hashtags(self):
        """No debe haber más de 3 hashtags en total."""
        respuesta_mock = json.dumps({
            "caption": "Test.",
            "hashtags": ["#uno", "#dos", "#tres", "#cuatro", "#cinco"],
        })
        with patch("ollama.generate") as mock_ollama:
            mock_ollama.return_value = {"response": respuesta_mock}
            from agents.copy_agent import generar_caption
            resultado = generar_caption(self.DIA_PRUEBA)

        self.assertLessEqual(len(resultado["hashtags"]), 3)


class TestCompositor(unittest.TestCase):
    """Verifica que el compositor genera una story con dimensiones correctas."""

    def test_dimensiones_story(self):
        """La story debe ser exactamente 1080x1920."""
        from PIL import Image

        from agents.compositor import STORY_H, STORY_W, montar_story

        # Crear imagen base de prueba
        img_prueba = Image.new("RGB", (800, 800), (15, 15, 25))
        img_path = BASE_DIR / "output" / "test_base.png"
        img_path.parent.mkdir(exist_ok=True)
        img_prueba.save(img_path)

        story_path = montar_story(
            image_path=img_path,
            caption="Caption de prueba para el test.",
            hashtags=["#MerakiBilbao", "#Santutxu", "#Test"],
            fecha="2026-01-01",
            dia_semana="test",
            output_path=BASE_DIR / "output" / "test_story.png",
        )

        self.assertTrue(story_path.exists(), "El fichero de story no fue creado")
        with Image.open(story_path) as img:
            self.assertEqual(img.size, (STORY_W, STORY_H),
                             f"Dimensiones incorrectas: {img.size} != ({STORY_W}, {STORY_H})")

    def tearDown(self):
        # Limpiar ficheros de prueba
        for f in ["test_base.png", "test_story.png"]:
            p = BASE_DIR / "output" / f
            if p.exists():
                p.unlink()


class TestPublisher(unittest.TestCase):
    """Verifica el publisher en modo DRY_RUN."""

    def test_dry_run_no_llama_a_api(self):
        """Con DRY_RUN=true no debe hacer ninguna llamada HTTP."""
        os.environ["DRY_RUN"] = "true"
        from core.publisher import publicar_story

        dia_prueba = {
            "fecha": "2026-06-04",
            "dia_semana": "miercoles",
            "caption": "Test caption.",
            "hashtags": ["#MerakiBilbao"],
            "story_path": str(BASE_DIR / "output" / "test.jpg"),
        }

        with patch("requests.post") as mock_post:
            resultado = publicar_story(dia_prueba)
            mock_post.assert_not_called()

        self.assertEqual(resultado["estado"], "simulado")
        self.assertEqual(resultado["media_id"], "DRY_RUN_NO_ID")

    def test_dry_run_devuelve_estructura_correcta(self):
        """El resultado DRY_RUN debe tener todos los campos esperados."""
        os.environ["DRY_RUN"] = "true"
        from core.publisher import publicar_story

        dia = {
            "fecha": "2026-06-04",
            "dia_semana": "miercoles",
            "caption": "Test.",
            "hashtags": [],
            "story_path": "",
        }
        resultado = publicar_story(dia)
        for campo in ["estado", "fecha", "dia_semana", "media_id"]:
            self.assertIn(campo, resultado, f"Falta campo '{campo}' en resultado DRY_RUN")


class TestPipelineIntegrado(unittest.TestCase):
    """
    Test end-to-end del pipeline completo mockeando Ollama y SDXL.
    No requiere GPU ni servicios externos.
    """

    def test_pipeline_completo_sin_publicar(self):
        """
        Ejecuta planner → copy → compositor → publisher (DRY_RUN).
        SDXL se mockea para no usar GPU en el test.
        """
        from PIL import Image

        # Limpiar estado previo
        state_file = BASE_DIR / "state" / "weekly_plan.json"
        if state_file.exists():
            state_file.unlink()

        respuesta_plan = {"response": "Cócteles de verano para arrancar la semana."}
        respuesta_copy = json.dumps({
            "caption": "¡Arranca la semana con energía en Meraki!",
            "hashtags": ["#CoctelesDeTemporada", "#MerakiBilbao", "#Santutxu"],
        })

        # Imagen base simulada (800x800 oscura)
        img_simulada = Image.new("RGB", (800, 800), (10, 10, 20))
        img_path_simulada = BASE_DIR / "output" / "pipeline_test_base.png"
        img_path_simulada.parent.mkdir(exist_ok=True)
        img_simulada.save(img_path_simulada)

        os.environ["DRY_RUN"] = "true"

        with patch("ollama.generate") as mock_ollama, \
             patch("agents.image_agent.generar_imagen", return_value=img_path_simulada):

            mock_ollama.return_value = {"response": respuesta_plan}

            # Planner
            from agents.planner import generar_plan_semanal
            plan = generar_plan_semanal(forzar=True)
            self.assertEqual(len(plan), 7)

            # Tomar un día del plan y completar el pipeline
            fecha, dia = next(iter(plan.items()))

            mock_ollama.return_value = {"response": respuesta_copy}
            from agents.copy_agent import generar_caption
            copy_result = generar_caption(dia)
            dia["caption"] = copy_result["caption"]
            dia["hashtags"] = copy_result["hashtags"]

            # Compositor (usa Pillow real)
            from agents.compositor import montar_story
            story_path = montar_story(
                image_path=img_path_simulada,
                caption=dia["caption"],
                hashtags=dia["hashtags"],
                fecha=fecha,
                dia_semana=dia["dia_semana"],
                output_path=BASE_DIR / "output" / "pipeline_test_story.png",
            )
            self.assertTrue(story_path.exists())
            dia["story_path"] = str(story_path)

            # Publisher DRY_RUN
            from core.publisher import publicar_story
            resultado = publicar_story(dia)
            self.assertEqual(resultado["estado"], "simulado")

        logger.info(f"✓ Pipeline completo OK para {dia['dia_semana']} {fecha}")

    def tearDown(self):
        for f in ["pipeline_test_base.png", "pipeline_test_story.png"]:
            p = BASE_DIR / "output" / f
            if p.exists():
                p.unlink()


if __name__ == "__main__":
    print("\n══ Tests Meraki Bot ══════════════════════════════════════")
    print("  Sin GPU, sin credenciales, sin servicios externos\n")
    unittest.main(verbosity=2)
