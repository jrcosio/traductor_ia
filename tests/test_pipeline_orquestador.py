from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
import wave

import numpy as np


SRC_PATH = Path(__file__).resolve().parents[1] / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from traductor_tiempo_real.asr.modelos import AsrResult
from traductor_tiempo_real.configuracion.carga import build_default_app_config
from traductor_tiempo_real.pipeline.orquestador import run_pre_recorded_pipeline
from traductor_tiempo_real.traduccion.modelos import TranslationResult
from traductor_tiempo_real.tts.modelos import TtsResult


class _FakeAsrService:
    def __init__(self) -> None:
        self._results = []

    @property
    def unfinished_tasks(self) -> int:
        return 0

    def submit_final(self, segment) -> None:
        self._results.append(
            AsrResult(
                request_id="asr-1",
                utterance_id=segment.segment_id,
                is_final=True,
                text="hola prueba",
                language="es",
                created_at=segment.created_at,
                started_at=segment.started_at,
                finished_at=segment.finished_at + 0.1,
                latency_ms=100.0,
                source_duration_ms=segment.duration_ms,
            )
        )

    def poll_results(self):
        drained = list(self._results)
        self._results.clear()
        return drained

    def wait_until_drained(self, timeout_seconds=30.0):
        return None

    def close(self):
        return None

    def join(self, timeout=None):
        return None


class _FakeTranslationService:
    def __init__(self) -> None:
        self._results = []

    @property
    def unfinished_tasks(self) -> int:
        return 0

    def submit_asr_result(self, asr_result, *, target_language: str):
        self._results.append(
            TranslationResult(
                request_id="tr-1",
                utterance_id=asr_result.utterance_id,
                status="translated",
                text="hello test",
                source_text=asr_result.text,
                source_language=asr_result.language,
                target_language=target_language,
                created_at=asr_result.created_at,
                started_at=asr_result.finished_at,
                finished_at=asr_result.finished_at + 0.1,
                latency_ms=100.0,
                model="fake-model",
            )
        )

    def poll_results(self):
        drained = list(self._results)
        self._results.clear()
        return drained

    def wait_until_drained(self, timeout_seconds=30.0):
        return None

    def close(self):
        return None

    def join(self, timeout=None):
        return None


class _FakeTtsService:
    def __init__(self) -> None:
        self._results = []

    @property
    def unfinished_tasks(self) -> int:
        return 0

    def submit_translation_result(self, translation_result):
        self._results.append(
            TtsResult(
                request_id="tts-1",
                utterance_id=translation_result.utterance_id,
                status="played",
                language=translation_result.target_language,
                voice="af_heart",
                text=translation_result.text,
                created_at=translation_result.created_at,
                started_at=translation_result.finished_at,
                finished_at=translation_result.finished_at + 0.2,
                time_to_first_audio_ms=50.0,
                total_synthesis_ms=200.0,
                playback_duration_ms=1000.0,
                sample_rate=24000,
            )
        )

    def poll_results(self):
        drained = list(self._results)
        self._results.clear()
        return drained

    def wait_until_drained(self, timeout_seconds=30.0):
        return None

    def close(self):
        return None

    def join(self, timeout=None):
        return None


class _FakeRuntime:
    def __init__(self) -> None:
        self.translation = type("TranslationRuntime", (), {})()
        self.translation.asr = type("AsrRuntime", (), {})()
        self.translation.asr.device_info = {"name": "Fake Mic"}
        self.translation.asr.detector = None
        self.translation.asr.events = []
        self.translation.asr.checks = []
        self.translation.asr.asr_service = _FakeAsrService()
        self.translation.translation_service = _FakeTranslationService()
        self.translation.events = []
        self.translation.checks = []
        self.tts = type("TtsRuntime", (), {})()
        self.tts.output_device_info = {"name": "Fake Output"}
        self.tts.tts_service = _FakeTtsService()
        self.tts.events = []
        self.tts.checks = []


class PipelineOrquestadorTestCase(unittest.TestCase):
    def test_pipeline_pregrabado_recorre_todas_las_etapas(self) -> None:
        config = build_default_app_config(target_language="en")

        with tempfile.TemporaryDirectory() as tmp_dir:
            sample_path = Path(tmp_dir) / "sample.wav"
            audio = (np.zeros(16000, dtype=np.int16)).tobytes()
            with wave.open(str(sample_path), "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(16000)
                wav_file.writeframes(audio)

            from unittest.mock import patch

            with patch("traductor_tiempo_real.pipeline.orquestador.bootstrap_speech_runtime", return_value=_FakeRuntime()):
                report = run_pre_recorded_pipeline(config, sample_paths=[sample_path], play_audio=False)

        self.assertEqual(report.segments_emitted, 1)
        self.assertEqual(len(report.asr_results), 1)
        self.assertEqual(len(report.translation_results), 1)
        self.assertEqual(len(report.tts_results), 1)
        self.assertEqual(report.translation_results[0].status, "translated")
        self.assertEqual(report.tts_results[0].status, "played")
        self.assertIn("segments", report.queue_stats.maxsizes)
        self.assertTrue(report.events)
        self.assertEqual(report.latency_summary()["end_to_end_to_first_audio"]["count"], 1)
        self.assertIn("latency_summary", report.to_dict())


if __name__ == "__main__":
    unittest.main()
