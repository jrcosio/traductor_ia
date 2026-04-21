from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch


SRC_PATH = Path(__file__).resolve().parents[1] / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from traductor_tiempo_real.configuracion.carga import build_default_app_config
from traductor_tiempo_real.traduccion.modelos import TranslationResult
from traductor_tiempo_real.tts.diagnostico import run_guided_speech_validation


class _FakeTtsService:
    def __init__(self) -> None:
        self.submitted = []

    def submit_translation_result(self, result) -> None:
        self.submitted.append(result)

    def close(self) -> None:
        return None

    def join(self, timeout=None) -> None:
        return None

    def close(self) -> None:
        return None

    def join(self, timeout=None) -> None:
        return None


class _FakeService:
    def close(self) -> None:
        return None

    def join(self, timeout=None) -> None:
        return None


class _FakeTranslationService(_FakeService):
    def __init__(self, result_callback) -> None:
        self.result_callback = result_callback


class _FakeRuntime:
    def __init__(self, result_callback) -> None:
        self.translation = type("TranslationRuntime", (), {})()
        self.translation.translation_service = _FakeTranslationService(result_callback)
        self.translation.asr = type("AsrRuntime", (), {})()
        self.translation.asr.asr_service = _FakeService()
        self.tts = type("TtsRuntime", (), {})()
        self.tts.tts_service = _FakeTtsService()


class TtsDiagnosticoTestCase(unittest.TestCase):
    def test_validacion_guiada_reenvia_traduccion_a_tts(self) -> None:
        config = build_default_app_config(target_language="en")
        runtime_holder: dict[str, object] = {}
        translation_events: list[TranslationResult] = []

        def fake_bootstrap(config, *, on_step=None, translation_result_callback=None, tts_result_callback=None, play_audio=True):
            runtime = _FakeRuntime(translation_result_callback)
            runtime_holder["runtime"] = runtime
            return runtime

        def fake_run_live_speech(config, *, duration_seconds, max_segments, play_audio, on_asr_result, runtime):
            result = TranslationResult(
                request_id="tr-1",
                utterance_id="utt-1",
                status="translated",
                text="Hello, this is a test.",
                source_text="Hola, esto es una prueba.",
                source_language="es",
                target_language="en",
                created_at=0.0,
                started_at=0.0,
                finished_at=0.1,
                latency_ms=100.0,
                model="gemma4:26b",
            )
            runtime.translation.translation_service.result_callback(result)
            return type(
                "FakeSpeechReport",
                (),
                {
                    "translation_report": type("FakeTranslationReport", (), {"translations": [result]})(),
                    "tts_results": [type("FakeTtsResult", (), {"status": "played"})()],
                    "is_successful": lambda self: True,
                },
            )()

        with (
            patch("traductor_tiempo_real.tts.diagnostico.bootstrap_speech_runtime", fake_bootstrap),
            patch("traductor_tiempo_real.tts.diagnostico.run_live_speech", fake_run_live_speech),
        ):
            report = run_guided_speech_validation(
                config,
                script_name="es-basico",
                play_audio=False,
                on_translation_result=translation_events.append,
                wait_callback=lambda: None,
            )

        runtime = runtime_holder["runtime"]
        self.assertEqual(len(runtime.tts.tts_service.submitted), 2)
        self.assertEqual(len(translation_events), 2)
        self.assertTrue(report.is_successful())
        self.assertEqual(report.entries[0].spoken_status, "played")


if __name__ == "__main__":
    unittest.main()
