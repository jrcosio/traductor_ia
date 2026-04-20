from __future__ import annotations

from pathlib import Path

from traductor_tiempo_real.configuracion.idiomas import LanguageCode, parse_target_language
from traductor_tiempo_real.configuracion.modelos import AppConfig, AudioConfig, BenchmarkConfig, TranslationConfig, VadConfig


def resolve_project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def build_default_app_config(target_language: str | LanguageCode = LanguageCode.EN, debug: bool = False) -> AppConfig:
    project_root = resolve_project_root()
    return AppConfig(
        project_root=project_root,
        source_language="auto",
        target_language=parse_target_language(target_language),
        audio=AudioConfig(),
        vad=VadConfig(),
        translation=TranslationConfig(),
        benchmark=BenchmarkConfig(default_sample=project_root / "samples" / "base_silence.wav"),
        debug=debug,
    )
