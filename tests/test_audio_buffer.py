from __future__ import annotations

from pathlib import Path
import sys
from time import monotonic
import unittest

import numpy as np


SRC_PATH = Path(__file__).resolve().parents[1] / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from traductor_tiempo_real.audio.captura import AudioRingBuffer
from traductor_tiempo_real.audio.modelos import AudioFrame


def build_frame(value: float, frame_id: str) -> AudioFrame:
    return AudioFrame(
        frame_id=frame_id,
        created_at=monotonic(),
        sample_rate=16000,
        channels=1,
        frame_count=512,
        audio=np.full(512, value, dtype=np.float32),
    )


class AudioRingBufferTestCase(unittest.TestCase):
    def test_conserva_orden_fifo(self) -> None:
        buffer = AudioRingBuffer(max_frames=3)
        first = build_frame(0.1, "a")
        second = build_frame(0.2, "b")

        buffer.push(first)
        buffer.push(second)

        self.assertEqual(buffer.pop(timeout=0), first)
        self.assertEqual(buffer.pop(timeout=0), second)

    def test_descarta_el_mas_antiguo_si_se_llena(self) -> None:
        buffer = AudioRingBuffer(max_frames=2)
        first = build_frame(0.1, "a")
        second = build_frame(0.2, "b")
        third = build_frame(0.3, "c")

        buffer.push(first)
        buffer.push(second)
        buffer.push(third)

        self.assertEqual(buffer.dropped_chunks, 1)
        self.assertEqual(buffer.pop(timeout=0), second)
        self.assertEqual(buffer.pop(timeout=0), third)


if __name__ == "__main__":
    unittest.main()
