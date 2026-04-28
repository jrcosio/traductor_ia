from __future__ import annotations

from pathlib import Path
import sys
import unittest


SRC_PATH = Path(__file__).resolve().parents[1] / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from traductor_tiempo_real.configuracion.modelos import TtsConfig
from traductor_tiempo_real.tts.kokoro import build_voice_map, get_voice_for_language


class TtsKokoroTestCase(unittest.TestCase):
    def test_mapea_voces_por_idioma(self) -> None:
        voice_map = build_voice_map(TtsConfig())
        self.assertEqual(voice_map["en"], "af_heart")
        self.assertEqual(voice_map["es"], "ef_dora")
        self.assertEqual(voice_map["fr"], "ff_siwis")
        self.assertEqual(voice_map["it"], "if_sara")

    def test_idioma_no_configurado_no_tiene_voz(self) -> None:
        self.assertIsNone(get_voice_for_language("pt", TtsConfig()))


if __name__ == "__main__":
    unittest.main()
