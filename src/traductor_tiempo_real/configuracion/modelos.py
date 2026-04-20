from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from traductor_tiempo_real.configuracion.idiomas import LanguageCode


@dataclass(frozen=True, slots=True)
class AudioConfig:
    sample_rate: int = 16000
    channels: int = 1
    chunk_ms: int = 32
    dtype: str = "float32"
    blocksize: int = 512
    device: int | str | None = None
    queue_max_frames: int = 128
    capture_channels: int = 1


@dataclass(frozen=True, slots=True)
class VadConfig:
    threshold: float = 0.5
    window_ms: int = 32
    pre_roll_ms: int = 96
    hangover_ms: int = 160
    max_segment_ms: int = 15000


@dataclass(frozen=True, slots=True)
class TranslationConfig:
    backend: str = "ollama"
    preferred_model: str = "qwen3:8b"
    candidate_models: tuple[str, ...] = ("qwen3:8b", "gemma4:27b")


@dataclass(frozen=True, slots=True)
class BenchmarkConfig:
    default_sample: Path
    run_model_probe: bool = True


@dataclass(frozen=True, slots=True)
class AppConfig:
    project_root: Path
    source_language: str
    target_language: LanguageCode
    audio: AudioConfig
    vad: VadConfig
    translation: TranslationConfig
    benchmark: BenchmarkConfig
    debug: bool = False
