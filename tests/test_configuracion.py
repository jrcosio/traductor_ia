from __future__ import annotations

from pathlib import Path
import sys
import unittest


SRC_PATH = Path(__file__).resolve().parents[1] / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from traductor_tiempo_real.configuracion.carga import build_default_app_config
from traductor_tiempo_real.configuracion.idiomas import LanguageCode


class ConfiguracionTestCase(unittest.TestCase):
    def test_construye_configuracion_por_defecto(self) -> None:
        config = build_default_app_config()
        self.assertEqual(config.source_language, "auto")
        self.assertEqual(config.target_language, LanguageCode.EN)
        self.assertEqual(config.audio.sample_rate, 16000)
        self.assertEqual(config.audio.blocksize, 512)
        self.assertEqual(config.vad.window_ms, 32)
        self.assertEqual(config.asr.backend, "mlx-whisper")
        self.assertEqual(config.asr.model_repo, "mlx-community/whisper-large-v3-turbo")
        self.assertTrue(config.benchmark.default_sample.name.endswith(".wav"))

    def test_permita_idioma_destino_valido(self) -> None:
        config = build_default_app_config(target_language="it", debug=True)
        self.assertEqual(config.target_language, LanguageCode.IT)
        self.assertTrue(config.debug)

    def test_falla_con_idioma_destino_invalido(self) -> None:
        with self.assertRaises(ValueError):
            build_default_app_config(target_language="pt")


if __name__ == "__main__":
    unittest.main()
