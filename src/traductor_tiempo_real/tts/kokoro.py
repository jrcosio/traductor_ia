from __future__ import annotations

import logging
import os
import warnings
from collections.abc import Iterator

import numpy as np

from traductor_tiempo_real.configuracion.modelos import TtsConfig


VOICE_LANG_CODE = {
    "en": "a",
    "es": "e",
    "fr": "f",
    "it": "i",
}


def build_voice_map(config: TtsConfig) -> dict[str, str | None]:
    return dict(config.voice_by_language)


def get_voice_for_language(language: str, config: TtsConfig) -> str | None:
    return build_voice_map(config).get(language.lower())


class KokoroTtsBackend:
    def __init__(self, config: TtsConfig) -> None:
        self._config = config
        self._pipelines: dict[str, object] = {}

    def supports_language(self, language: str) -> bool:
        normalized = language.lower()
        return normalized in VOICE_LANG_CODE and get_voice_for_language(normalized, self._config) is not None

    def warmup(self, language: str) -> None:
        if not self.supports_language(language):
            return
        voice = get_voice_for_language(language, self._config)
        if voice is None:
            return
        pipeline = self._get_pipeline(language)
        generator = pipeline("Hola." if language == "es" else "Hello.", voice=voice, speed=self._config.speed)
        next(generator)

    def synthesize(self, text: str, *, language: str) -> Iterator[np.ndarray]:
        normalized = language.lower()
        voice = get_voice_for_language(normalized, self._config)
        if voice is None:
            raise ValueError(f"No hay voz Kokoro configurada para el idioma {language}")

        pipeline = self._get_pipeline(normalized)
        generator = pipeline(
            text,
            voice=voice,
            speed=self._config.speed,
            split_pattern=self._config.split_pattern,
        )
        for chunk in generator:
            audio = chunk.audio
            if hasattr(audio, "detach"):
                audio = audio.detach()
            if hasattr(audio, "cpu"):
                audio = audio.cpu()
            if hasattr(audio, "numpy"):
                audio = audio.numpy()
            yield np.asarray(audio, dtype=np.float32).reshape(-1)

    def _get_pipeline(self, language: str):
        normalized = language.lower()
        if normalized not in self._pipelines:
            os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
            os.environ.setdefault("HF_HUB_VERBOSITY", "error")
            logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
            logging.getLogger("huggingface_hub.file_download").setLevel(logging.ERROR)
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message="dropout option adds dropout.*")
                warnings.filterwarnings("ignore", message="`torch.nn.utils.weight_norm` is deprecated.*")
                warnings.filterwarnings("ignore", message="Warning: You are sending unauthenticated requests to the HF Hub.*")
                from kokoro import KPipeline

                self._pipelines[normalized] = KPipeline(
                    lang_code=VOICE_LANG_CODE[normalized],
                    repo_id=self._config.repo_id,
                )
        return self._pipelines[normalized]
