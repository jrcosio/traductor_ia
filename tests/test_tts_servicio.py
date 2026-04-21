from __future__ import annotations

from pathlib import Path
import sys
import time
import unittest

import numpy as np


SRC_PATH = Path(__file__).resolve().parents[1] / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from traductor_tiempo_real.configuracion.modelos import TtsConfig
from traductor_tiempo_real.traduccion.modelos import TranslationResult
from traductor_tiempo_real.tts.servicio import TtsProcessingService


class FakeTtsBackend:
    def __init__(self) -> None:
        self.warmup_calls = []
        self.synthesize_calls = []

    def supports_language(self, language: str) -> bool:
        return language in {"en", "es", "fr", "it"}

    def warmup(self, language: str) -> None:
        self.warmup_calls.append(language)

    def synthesize(self, text: str, *, language: str):
        time.sleep(0.05)
        self.synthesize_calls.append((text, language))
        yield np.ones(2400, dtype=np.float32) * 0.1
        yield np.ones(1200, dtype=np.float32) * 0.2


class FakeAudioPlayer:
    def __init__(self) -> None:
        self.play_calls = []

    def play_chunks(self, chunks, *, sample_rate: int, play_audio: bool = True):
        total = 0
        for chunk in chunks:
            total += len(chunk)
        self.play_calls.append((sample_rate, play_audio, total))
        return {
            "audio_duration_ms": (total / sample_rate) * 1000,
            "sample_count": float(total),
            "first_chunk_ready": 1.0,
        }


def build_translation_result(status: str, *, language: str, target_language: str, text: str, source_text: str | None = None, skip_reason: str | None = None) -> TranslationResult:
    return TranslationResult(
        request_id="tr-1",
        utterance_id="utt-1",
        status=status,
        text=text,
        source_text=source_text or text,
        source_language=language,
        target_language=target_language,
        created_at=0.0,
        started_at=0.0,
        finished_at=0.1,
        latency_ms=100.0,
        model="gemma4:26b",
        skip_reason=skip_reason,
    )


class TtsServicioTestCase(unittest.TestCase):
    def test_reproduce_traduccion_final(self) -> None:
        backend = FakeTtsBackend()
        player = FakeAudioPlayer()
        service = TtsProcessingService(
            TtsConfig(warmup_on_start=False),
            target_language="en",
            backend=backend,
            player=player,
            play_audio=False,
        ).start()

        service.submit_translation_result(
            build_translation_result(
                "translated",
                language="es",
                target_language="en",
                text="Hello, this is a test.",
                source_text="Hola, esto es una prueba.",
            )
        )
        service.wait_until_drained(timeout_seconds=2.0)
        service.close()
        service.join(timeout=2.0)

        results = service.poll_results()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, "played")
        self.assertEqual(results[0].voice, "af_heart")
        self.assertEqual(len(backend.synthesize_calls), 1)
        self.assertEqual(len(player.play_calls), 1)

    def test_si_traduccion_se_omite_y_destino_igual_habla_texto_fuente(self) -> None:
        backend = FakeTtsBackend()
        player = FakeAudioPlayer()
        service = TtsProcessingService(
            TtsConfig(warmup_on_start=False),
            target_language="en",
            backend=backend,
            player=player,
            play_audio=False,
        ).start()

        service.submit_translation_result(
            build_translation_result(
                "skipped",
                language="en",
                target_language="en",
                text="",
                source_text="This is already English.",
                skip_reason="source_equals_target",
            )
        )
        service.wait_until_drained(timeout_seconds=2.0)
        service.close()
        service.join(timeout=2.0)

        results = service.poll_results()
        self.assertEqual(results[0].status, "played")
        self.assertEqual(backend.synthesize_calls[0][0], "This is already English.")

    def test_omite_idioma_no_soportado(self) -> None:
        backend = FakeTtsBackend()
        player = FakeAudioPlayer()
        service = TtsProcessingService(
            TtsConfig(warmup_on_start=False),
            target_language="de",
            backend=backend,
            player=player,
            play_audio=False,
        ).start()

        service.submit_translation_result(
            build_translation_result(
                "translated",
                language="en",
                target_language="de",
                text="Hallo, das ist ein Test.",
            )
        )
        service.close()
        service.join(timeout=2.0)

        results = service.poll_results()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, "skipped")
        self.assertEqual(results[0].skip_reason, "unsupported_language")
        self.assertEqual(backend.synthesize_calls, [])


if __name__ == "__main__":
    unittest.main()
