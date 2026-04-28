from __future__ import annotations

from pathlib import Path
import sys
import time
import unittest


SRC_PATH = Path(__file__).resolve().parents[1] / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from traductor_tiempo_real.asr.modelos import AsrResult
from traductor_tiempo_real.configuracion.modelos import TranslationConfig
from traductor_tiempo_real.traduccion.servicio import TranslationProcessingService


class FakeTranslationBackend:
    def __init__(self) -> None:
        self.warmup_called = False
        self.calls = []

    def warmup(self) -> None:
        self.warmup_called = True

    def translate(self, source_text: str, *, source_language: str | None, target_language: str):
        time.sleep(0.05)
        self.calls.append((source_text, source_language, target_language))
        return f"trad:{source_text}", {"parse_mode": "json"}


def build_asr_result(text: str, language: str) -> AsrResult:
    return AsrResult(
        request_id="asr-1",
        utterance_id="utt-1",
        is_final=True,
        text=text,
        language=language,
        created_at=0.0,
        started_at=0.0,
        finished_at=0.1,
        latency_ms=100.0,
        source_duration_ms=1000.0,
    )


class TraduccionServicioTestCase(unittest.TestCase):
    def test_omite_traduccion_si_origen_igual_destino(self) -> None:
        backend = FakeTranslationBackend()
        service = TranslationProcessingService(
            TranslationConfig(warmup_on_start=False),
            backend=backend,
        ).start()

        service.submit_asr_result(build_asr_result("Hello, this is a test.", "en"), target_language="en")
        service.close()
        service.join(timeout=2.0)

        results = service.poll_results()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, "skipped")
        self.assertEqual(results[0].skip_reason, "source_equals_target")
        self.assertEqual(backend.calls, [])

    def test_traduce_si_origen_y_destino_difieren(self) -> None:
        backend = FakeTranslationBackend()
        service = TranslationProcessingService(
            TranslationConfig(warmup_on_start=False),
            backend=backend,
        ).start()

        service.submit_asr_result(build_asr_result("Hola, esto es una prueba.", "es"), target_language="en")
        service.wait_until_drained(timeout_seconds=2.0)
        service.close()
        service.join(timeout=2.0)

        results = service.poll_results()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, "translated")
        self.assertEqual(results[0].text, "trad:Hola, esto es una prueba.")
        self.assertEqual(len(backend.calls), 1)

    def test_acota_cola_interna_de_traduccion(self) -> None:
        checks = []
        service = TranslationProcessingService(
            TranslationConfig(warmup_on_start=False, queue_max_items=1),
            backend=FakeTranslationBackend(),
            checks=checks,
        )

        service.submit_asr_result(build_asr_result("Primera frase.", "es"), target_language="en")
        service.submit_asr_result(build_asr_result("Segunda frase.", "es"), target_language="en")

        self.assertEqual(service.unfinished_tasks, 1)
        self.assertEqual(checks[-1].name, "translation.queue")


if __name__ == "__main__":
    unittest.main()
