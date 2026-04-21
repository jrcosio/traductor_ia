from __future__ import annotations

from pathlib import Path
import sys
from time import monotonic
import unittest

import numpy as np


SRC_PATH = Path(__file__).resolve().parents[1] / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from traductor_tiempo_real.audio.modelos import AudioFrame
from traductor_tiempo_real.configuracion.modelos import AudioConfig, VadConfig
from traductor_tiempo_real.vad.segmentador import SpeechSegmenter


def build_frame(index: int, amplitude: float = 0.0) -> AudioFrame:
    return AudioFrame(
        frame_id=f"frame-{index}",
        created_at=monotonic() + (index * 0.032),
        sample_rate=16000,
        channels=1,
        frame_count=512,
        audio=np.full(512, amplitude, dtype=np.float32),
    )


class SegmentadorTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.audio_config = AudioConfig(blocksize=512, sample_rate=16000)
        self.vad_config = VadConfig(pre_roll_ms=64, hangover_ms=96, max_segment_ms=1000)

    def test_silencio_no_emite_segmentos(self) -> None:
        segmenter = SpeechSegmenter(self.audio_config, self.vad_config)
        segments = []
        for index in range(8):
            segments.extend(segmenter.process_frame(build_frame(index), is_speech=False))
        segments.extend(segmenter.flush())
        self.assertEqual(segments, [])

    def test_pre_roll_y_hangover_generan_un_unico_segmento(self) -> None:
        segmenter = SpeechSegmenter(self.audio_config, self.vad_config)
        pattern = [False, False, True, True, True, False, False, True, True, False, False, False]
        segments = []
        for index, is_speech in enumerate(pattern):
            amplitude = 0.8 if is_speech else 0.0
            segments.extend(segmenter.process_frame(build_frame(index, amplitude), is_speech=is_speech))

        self.assertEqual(len(segments), 1)
        segment = segments[0]
        self.assertGreater(segment.duration_ms, 0)
        self.assertGreater(segment.energy_rms, 0)
        self.assertEqual(segment.metadata["reason"], "hangover")

    def test_voz_continua_emite_segmento_al_hacer_flush(self) -> None:
        segmenter = SpeechSegmenter(self.audio_config, self.vad_config)
        segments = []
        for index in range(6):
            segments.extend(segmenter.process_frame(build_frame(index, 0.9), is_speech=True))

        segments.extend(segmenter.flush())

        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0].metadata["reason"], "flush")
        self.assertGreaterEqual(segments[0].closure_latency_ms, 0)

    def test_cierra_por_duracion_maxima(self) -> None:
        segmenter = SpeechSegmenter(self.audio_config, VadConfig(pre_roll_ms=32, hangover_ms=160, max_segment_ms=160))
        segments = []
        for index in range(8):
            segments.extend(segmenter.process_frame(build_frame(index, 0.7), is_speech=True))

        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0].metadata["reason"], "max_segment")

    def test_snapshot_activo_usa_mismo_segment_id_que_el_final(self) -> None:
        segmenter = SpeechSegmenter(self.audio_config, self.vad_config)
        for index in range(4):
            segmenter.process_frame(build_frame(index, 0.7), is_speech=True)

        snapshot = segmenter.snapshot()
        self.assertIsNotNone(snapshot)
        self.assertGreater(snapshot.duration_ms, 0)

        final = segmenter.flush()[0]
        self.assertEqual(snapshot.segment_id, final.segment_id)

    def test_ruido_sin_voz_no_emite_segmentos(self) -> None:
        segmenter = SpeechSegmenter(self.audio_config, self.vad_config)
        segments = []
        for index in range(6):
            segments.extend(segmenter.process_frame(build_frame(index, 0.03), is_speech=False))
        self.assertEqual(segments, [])


if __name__ == "__main__":
    unittest.main()
