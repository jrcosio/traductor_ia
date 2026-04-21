from __future__ import annotations

from pathlib import Path
import sys
import unittest

import numpy as np


SRC_PATH = Path(__file__).resolve().parents[1] / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from traductor_tiempo_real.asr.diagnostico import _compute_language_stability
from traductor_tiempo_real.asr.servicio import AsrProcessingService
from traductor_tiempo_real.audio.modelos import ActiveSpeechSnapshot, SpeechSegment
from traductor_tiempo_real.configuracion.modelos import AsrConfig


class FakeBackend:
    def __init__(self) -> None:
        self.warmup_called = False
        self.calls = []

    def warmup(self) -> None:
        self.warmup_called = True

    def transcribe(self, audio: np.ndarray, *, sample_rate: int):
        self.calls.append((audio.copy(), sample_rate))
        text = f"frames={audio.size}"
        language = "es" if audio.mean() >= 0 else "en"
        return text, language, {"backend": "fake"}


class AsrServiceTestCase(unittest.TestCase):
    def test_procesa_partial_y_final(self) -> None:
        backend = FakeBackend()
        service = AsrProcessingService(
            AsrConfig(warmup_on_start=False),
            backend=backend,
        ).start()

        snapshot = ActiveSpeechSnapshot(
            segment_id="seg-1",
            created_at=1.0,
            started_at=0.5,
            updated_at=1.0,
            duration_ms=640.0,
            sample_rate=16000,
            frame_count=2,
            samples=np.ones(1024, dtype=np.float32),
            energy_rms=0.8,
        )
        segment = SpeechSegment(
            segment_id="seg-1",
            created_at=1.2,
            started_at=0.5,
            finished_at=1.1,
            duration_ms=700.0,
            closure_latency_ms=120.0,
            sample_rate=16000,
            frame_count=3,
            samples=np.ones(1536, dtype=np.float32),
            energy_rms=0.9,
        )

        service.submit_partial(snapshot)
        service.submit_final(segment)
        service.wait_until_drained(timeout_seconds=2.0)
        service.close()
        service.join(timeout=2.0)

        results = service.poll_results()
        self.assertEqual(len(results), 2)
        self.assertEqual(sum(1 for result in results if result.is_final), 1)
        self.assertEqual(sum(1 for result in results if not result.is_final), 1)
        self.assertTrue(all(result.language == "es" for result in results))
        self.assertEqual(len(backend.calls), 2)

    def test_calcula_estabilidad_de_idioma(self) -> None:
        from traductor_tiempo_real.asr.modelos import AsrResult

        results = [
            AsrResult(
                request_id="1",
                utterance_id="utt",
                is_final=False,
                text="hola",
                language="es",
                created_at=0.0,
                started_at=0.0,
                finished_at=0.1,
                latency_ms=100.0,
                source_duration_ms=500.0,
            ),
            AsrResult(
                request_id="2",
                utterance_id="utt",
                is_final=False,
                text="hola mundo",
                language="es",
                created_at=0.1,
                started_at=0.1,
                finished_at=0.2,
                latency_ms=100.0,
                source_duration_ms=800.0,
            ),
            AsrResult(
                request_id="3",
                utterance_id="utt",
                is_final=True,
                text="hola mundo",
                language="es",
                created_at=0.2,
                started_at=0.2,
                finished_at=0.3,
                latency_ms=100.0,
                source_duration_ms=1000.0,
            ),
        ]

        stability = _compute_language_stability(results)
        self.assertEqual(stability["utt"]["final_language"], "es")
        self.assertEqual(stability["utt"]["stability_ratio"], 1.0)


if __name__ == "__main__":
    unittest.main()
