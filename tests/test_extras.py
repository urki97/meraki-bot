"""
Tests de los módulos de robustez: historial, config_check y limpieza.
Sin GPU, sin credenciales, sin servicios externos.
"""

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault("DRY_RUN", "true")


class TestHistorial(unittest.TestCase):
    """El historial registra publicaciones y devuelve captions recientes."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()) / "historial.json"

    def test_registro_y_lectura(self):
        from core.historial import registrar_publicacion, captions_recientes, ultimas

        dia = {
            "fecha": "2026-06-11", "dia_semana": "jueves", "tema": "pintxopote",
            "caption": "Jueves. Pintxo. Zurito.", "hashtags": ["#Pintxopote"],
        }
        resultados = {"instagram": {"estado": "simulado", "media_id": "x"}}

        registrar_publicacion(dia, resultados, ruta=self.tmp)

        self.assertEqual(captions_recientes(5, ruta=self.tmp), ["Jueves. Pintxo. Zurito."])
        entradas = ultimas(5, ruta=self.tmp)
        self.assertEqual(len(entradas), 1)
        self.assertEqual(entradas[0]["redes"], ["instagram"])

    def test_no_registra_errores(self):
        """Si todas las redes fallaron, no se añade entrada."""
        from core.historial import registrar_publicacion, ultimas

        dia = {"fecha": "2026-06-11", "dia_semana": "jueves", "caption": "x"}
        resultados = {"instagram": {"estado": "error", "error": "boom"}}

        registrar_publicacion(dia, resultados, ruta=self.tmp)
        self.assertEqual(ultimas(5, ruta=self.tmp), [])

    def test_historial_corrupto_no_revienta(self):
        """Un JSON ilegible se trata como historial vacío."""
        from core.historial import captions_recientes

        self.tmp.parent.mkdir(parents=True, exist_ok=True)
        self.tmp.write_text("esto no es json")
        self.assertEqual(captions_recientes(ruta=self.tmp), [])


class TestConfigCheck(unittest.TestCase):
    """La comprobación de configuración distingue errores de avisos."""

    def test_dry_run_no_bloquea(self):
        """En DRY_RUN las credenciales que faltan son avisos, no errores."""
        os.environ["DRY_RUN"] = "true"
        os.environ["PUBLISH_INSTAGRAM"] = "true"
        os.environ.pop("IG_USER_ID", None)
        os.environ.pop("IG_ACCESS_TOKEN", None)

        import importlib
        import core.config_check
        importlib.reload(core.config_check)

        errores, avisos = core.config_check.comprobar_env()
        self.assertEqual(errores, [])
        self.assertTrue(any("Instagram" in a for a in avisos))

    def test_produccion_bloquea_sin_credenciales(self):
        """Sin DRY_RUN, faltar credenciales de una red activa es error."""
        os.environ["DRY_RUN"] = "false"
        os.environ["PUBLISH_INSTAGRAM"] = "true"
        os.environ.pop("IG_USER_ID", None)
        os.environ.pop("IG_ACCESS_TOKEN", None)

        import importlib
        import core.config_check
        importlib.reload(core.config_check)

        errores, _ = core.config_check.comprobar_env()
        self.assertTrue(any("Instagram" in e for e in errores))
        os.environ["DRY_RUN"] = "true"  # restaurar

    def test_ficheros_del_repo_presentes(self):
        """Los yaml de config del repo existen — sin errores de ficheros."""
        from core.config_check import comprobar_ficheros
        errores, _ = comprobar_ficheros()
        self.assertEqual(errores, [])


class TestLimpieza(unittest.TestCase):
    """La limpieza borra solo imágenes antiguas."""

    def test_borra_viejas_conserva_nuevas(self):
        from core import scheduler

        output_dir = BASE_DIR / "output"
        output_dir.mkdir(exist_ok=True)

        vieja = output_dir / "test_limpieza_vieja.png"
        nueva = output_dir / "test_limpieza_nueva.png"
        vieja.write_bytes(b"x")
        nueva.write_bytes(b"x")
        # Fechar la vieja hace 40 días
        hace_40_dias = time.time() - 40 * 86400
        os.utime(vieja, (hace_40_dias, hace_40_dias))

        borrados = scheduler.limpiar_output_antiguo(dias=30)

        self.assertGreaterEqual(borrados, 1)
        self.assertFalse(vieja.exists())
        self.assertTrue(nueva.exists())
        nueva.unlink()


if __name__ == "__main__":
    unittest.main(verbosity=2)
