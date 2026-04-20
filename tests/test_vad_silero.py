from __future__ import annotations

from pathlib import Path
import sys
import unittest

import numpy as np


SRC_PATH = Path(__file__).resolve().parents[1] / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from traductor_tiempo_real.configuracion.modelos import VadConfig
from traductor_tiempo_real.vad.silero import SileroSpeechDetector


class SileroVadTestCase(unittest.TestCase):
    def test_puntua_silencio_con_probabilidad_baja(self) -> None:
        detector = SileroSpeechDetector(VadConfig())
        silence = np.zeros(512, dtype=np.float32)

        is_speech, score = detector.is_speech(silence, 16000)

        self.assertFalse(is_speech)
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)


if __name__ == "__main__":
    unittest.main()
