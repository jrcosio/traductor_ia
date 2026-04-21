from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from traductor_tiempo_real.asr.modelos import AsrResult, GuidedValidationReport, LiveTranscriptionReport
from traductor_tiempo_real.metricas.eventos import CheckResult, CheckStatus, MetricEvent


@dataclass(frozen=True, slots=True)
class TranslationRequest:
    request_id: str
    utterance_id: str
    created_at: float
    source_text: str
    source_language: str | None
    target_language: str
    is_final: bool
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TranslationResult:
    request_id: str
    utterance_id: str
    status: str
    text: str
    source_text: str
    source_language: str | None
    target_language: str
    created_at: float
    started_at: float
    finished_at: float
    latency_ms: float
    model: str
    metadata: dict[str, Any] = field(default_factory=dict)
    skip_reason: str | None = None
    error: str | None = None

    @property
    def is_final(self) -> bool:
        return True

    def is_successful(self) -> bool:
        return self.error is None

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "utterance_id": self.utterance_id,
            "status": self.status,
            "text": self.text,
            "source_text": self.source_text,
            "source_language": self.source_language,
            "target_language": self.target_language,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "latency_ms": self.latency_ms,
            "model": self.model,
            "metadata": self.metadata,
            "skip_reason": self.skip_reason,
            "error": self.error,
        }


@dataclass(frozen=True, slots=True)
class LiveTranslationReport:
    asr_report: LiveTranscriptionReport
    translations: list[TranslationResult] = field(default_factory=list)
    events: list[MetricEvent] = field(default_factory=list)
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def translated_count(self) -> int:
        return sum(1 for item in self.translations if item.status == "translated")

    @property
    def skipped_count(self) -> int:
        return sum(1 for item in self.translations if item.status == "skipped")

    @property
    def error_count(self) -> int:
        return sum(1 for item in self.translations if item.status == "error")

    def is_successful(self) -> bool:
        return self.asr_report.is_successful() and not any(
            check.status == CheckStatus.ERROR for check in self.checks
        ) and all(item.is_successful() or item.status == "skipped" for item in self.translations)

    def to_dict(self) -> dict[str, Any]:
        return {
            "asr_report": self.asr_report.to_dict(),
            "translated_count": self.translated_count,
            "skipped_count": self.skipped_count,
            "error_count": self.error_count,
            "translations": [item.to_dict() for item in self.translations],
            "events": [event.to_dict() for event in self.events],
            "checks": [check.to_dict() for check in self.checks],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False, default=str)


@dataclass(frozen=True, slots=True)
class GuidedTranslationEntry:
    prompt: str
    report: LiveTranslationReport
    asr_text: str
    translation_status: str
    translation_text: str
    detected_language: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "prompt": self.prompt,
            "asr_text": self.asr_text,
            "translation_status": self.translation_status,
            "translation_text": self.translation_text,
            "detected_language": self.detected_language,
            "report": self.report.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class GuidedTranslationReport:
    script_name: str
    entries: list[GuidedTranslationEntry] = field(default_factory=list)
    checks: list[CheckResult] = field(default_factory=list)

    def is_successful(self) -> bool:
        return not any(check.status == CheckStatus.ERROR for check in self.checks) and all(
            entry.report.is_successful() for entry in self.entries
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "script_name": self.script_name,
            "entries": [entry.to_dict() for entry in self.entries],
            "checks": [check.to_dict() for check in self.checks],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False, default=str)
