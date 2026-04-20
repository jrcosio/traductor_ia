from __future__ import annotations

import numpy as np

from traductor_tiempo_real.configuracion.modelos import VadConfig


class SileroSpeechDetector:
    def __init__(self, config: VadConfig) -> None:
        import torch
        from silero_vad import load_silero_vad

        self._torch = torch
        self._model = load_silero_vad()
        self._config = config

    def _window_size_samples(self, sample_rate: int) -> int:
        return int(round((self._config.window_ms / 1000) * sample_rate))

    def _prepare_window(self, audio: np.ndarray, sample_rate: int) -> np.ndarray:
        window_size = self._window_size_samples(sample_rate)
        chunk = np.asarray(audio, dtype=np.float32).reshape(-1)
        if chunk.size < window_size:
            padded = np.zeros(window_size, dtype=np.float32)
            padded[: chunk.size] = chunk
            return padded
        if chunk.size > window_size:
            return np.array(chunk[:window_size], dtype=np.float32, copy=True)
        return np.array(chunk, dtype=np.float32, copy=True)

    def score(self, audio: np.ndarray, sample_rate: int) -> float:
        if sample_rate != 16000:
            raise ValueError(f"Silero VAD del Sprint 1 solo soporta sample_rate=16000, recibido {sample_rate}")
        window = self._prepare_window(audio, sample_rate)
        return float(self._model(self._torch.from_numpy(window), sample_rate).item())

    def is_speech(self, audio: np.ndarray, sample_rate: int) -> tuple[bool, float]:
        score = self.score(audio, sample_rate)
        return score >= self._config.threshold, score
