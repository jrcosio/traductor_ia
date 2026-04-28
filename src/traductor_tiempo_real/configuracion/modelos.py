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
class AsrConfig:
    backend: str = "mlx-whisper"
    model_repo: str = "mlx-community/whisper-large-v3-turbo"
    detect_language: bool = True
    enable_partials: bool = True
    partial_interval_ms: int = 400
    min_partial_ms: int = 640
    no_speech_threshold: float = 0.6
    condition_on_previous_text: bool = False
    compression_ratio_threshold: float = 2.4
    logprob_threshold: float = -1.0
    warmup_on_start: bool = True
    queue_max_items: int = 8


@dataclass(frozen=True, slots=True)
class TranslationConfig:
    backend: str = "ollama"
    preferred_model: str = "gemma4:26b"
    candidate_models: tuple[str, ...] = ("gemma4:26b", "qwen3:8b")
    base_url: str = "http://localhost:11434"
    think: bool = False
    stream: bool = False
    temperature: float = 0.0
    num_predict: int = 64
    timeout_seconds: float = 120.0
    keep_alive: str = "10m"
    structured_output: bool = True
    warmup_on_start: bool = True
    queue_max_items: int = 4


@dataclass(frozen=True, slots=True)
class TtsConfig:
    backend: str = "kokoro"
    repo_id: str = "hexgrad/Kokoro-82M"
    sample_rate: int = 24000
    device: int | str | None = None
    channels: int = 1
    dtype: str = "float32"
    blocksize: int = 2048
    speed: float = 1.0
    split_pattern: str = r"(?<=[.!?])\s+"
    warmup_on_start: bool = True
    queue_max_items: int = 32
    voice_by_language: tuple[tuple[str, str | None], ...] = (
        ("en", "af_heart"),
        ("es", "ef_dora"),
        ("fr", "ff_siwis"),
        ("it", "if_sara"),
    )


@dataclass(frozen=True, slots=True)
class PipelineConfig:
    segments_queue_max_items: int = 4
    translation_queue_max_items: int = 4
    tts_queue_max_items: int = 4
    event_queue_max_items: int = 128
    dispatch_poll_interval_ms: int = 20


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
    asr: AsrConfig
    translation: TranslationConfig
    tts: TtsConfig
    pipeline: PipelineConfig
    benchmark: BenchmarkConfig
    debug: bool = False
