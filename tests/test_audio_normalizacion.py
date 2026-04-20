from __future__ import annotations

from pathlib import Path
import sys
import unittest

import numpy as np


SRC_PATH = Path(__file__).resolve().parents[1] / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from traductor_tiempo_real.audio.captura import normalize_audio_chunk


class AudioNormalizacionTestCase(unittest.TestCase):
    def test_mantiene_audio_mono(self) -> None:
        chunk = np.array([0.1, -0.2, 0.3], dtype=np.float32)
        normalized = normalize_audio_chunk(chunk)
        np.testing.assert_allclose(normalized, chunk)

    def test_convierte_estereo_a_mono(self) -> None:
        chunk = np.array([[1.0, -1.0], [0.5, 0.5]], dtype=np.float32)
        normalized = normalize_audio_chunk(chunk)
        np.testing.assert_allclose(normalized, np.array([0.0, 0.5], dtype=np.float32))


if __name__ == "__main__":
    unittest.main()
