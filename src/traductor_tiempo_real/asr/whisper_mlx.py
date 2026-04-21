from __future__ import annotations

import os

import numpy as np

from traductor_tiempo_real.configuracion.modelos import AsrConfig


class MlxWhisperBackend:
    def __init__(self, config: AsrConfig) -> None:
        self._config = config

    def warmup(self) -> None:
        silence = np.zeros(16000, dtype=np.float32)
        self.transcribe(silence, sample_rate=16000)

    def transcribe(self, audio: np.ndarray, *, sample_rate: int) -> tuple[str, str | None, dict[str, object]]:
        if sample_rate != 16000:
            raise ValueError(f"mlx-whisper del Sprint 2 solo soporta audio a 16000 Hz, recibido {sample_rate}")

        os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")

        import mlx_whisper

        waveform = np.asarray(audio, dtype=np.float32).reshape(-1)
        result = mlx_whisper.transcribe(
            waveform,
            path_or_hf_repo=self._config.model_repo,
            verbose=None,
            no_speech_threshold=self._config.no_speech_threshold,
            compression_ratio_threshold=self._config.compression_ratio_threshold,
            logprob_threshold=self._config.logprob_threshold,
            condition_on_previous_text=self._config.condition_on_previous_text,
        )
        text = result.get("text", "").strip()
        language = result.get("language")
        metadata = {
            "segment_count": len(result.get("segments", [])),
        }
        return text, language, metadata
