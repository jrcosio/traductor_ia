from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from traductor_tiempo_real.metricas.eventos import CheckResult, CheckStatus, MetricEvent
from traductor_tiempo_real.traduccion.modelos import LiveTranslationReport


@dataclass(frozen=True, slots=True)
class TtsRequest:
    request_id: str
    utterance_id: str
    created_at: float
    text: str
    language: str
    voice: str | None
    source_status: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TtsResult:
    request_id: str
    utterance_id: str
    status: str
    language: str
    voice: str | None
    text: str
    created_at: float
    started_at: float
    finished_at: float
    time_to_first_audio_ms: float
    total_synthesis_ms: float
    playback_duration_ms: float
    sample_rate: int
    metadata: dict[str, Any] = field(default_factory=dict)
    skip_reason: str | None = None
    error: str | None = None

    def is_successful(self) -> bool:
        return self.error is None

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "utterance_id": self.utterance_id,
            "status": self.status,
            "language": self.language,
            "voice": self.voice,
            "text": self.text,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "time_to_first_audio_ms": self.time_to_first_audio_ms,
            "total_synthesis_ms": self.total_synthesis_ms,
            "playback_duration_ms": self.playback_duration_ms,
            "sample_rate": self.sample_rate,
            "metadata": self.metadata,
            "skip_reason": self.skip_reason,
            "error": self.error,
        }


@dataclass(frozen=True, slots=True)
class TtsDiagnosticReport:
    language: str
    voice: str | None
    text: str
    result: TtsResult
    events: list[MetricEvent] = field(default_factory=list)
    checks: list[CheckResult] = field(default_factory=list)

    def is_successful(self) -> bool:
        return self.result.is_successful() and not any(check.status == CheckStatus.ERROR for check in self.checks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "language": self.language,
            "voice": self.voice,
            "text": self.text,
            "result": self.result.to_dict(),
            "events": [event.to_dict() for event in self.events],
            "checks": [check.to_dict() for check in self.checks],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False, default=str)


@dataclass(frozen=True, slots=True)
class LiveSpeechReport:
    translation_report: LiveTranslationReport
    tts_results: list[TtsResult] = field(default_factory=list)
    events: list[MetricEvent] = field(default_factory=list)
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def played_count(self) -> int:
        return sum(1 for item in self.tts_results if item.status == "played")

    @property
    def skipped_count(self) -> int:
        return sum(1 for item in self.tts_results if item.status == "skipped")

    @property
    def error_count(self) -> int:
        return sum(1 for item in self.tts_results if item.status == "error")

    def is_successful(self) -> bool:
        return self.translation_report.is_successful() and not any(
            check.status == CheckStatus.ERROR for check in self.checks
        ) and all(item.is_successful() or item.status == "skipped" for item in self.tts_results)

    def to_dict(self) -> dict[str, Any]:
        return {
            "translation_report": self.translation_report.to_dict(),
            "played_count": self.played_count,
            "skipped_count": self.skipped_count,
            "error_count": self.error_count,
            "tts_results": [item.to_dict() for item in self.tts_results],
            "events": [event.to_dict() for event in self.events],
            "checks": [check.to_dict() for check in self.checks],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False, default=str)


@dataclass(frozen=True, slots=True)
class GuidedSpeechEntry:
    prompt: str
    report: LiveSpeechReport
    translation_status: str
    spoken_status: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "prompt": self.prompt,
            "translation_status": self.translation_status,
            "spoken_status": self.spoken_status,
            "report": self.report.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class GuidedSpeechReport:
    script_name: str
    entries: list[GuidedSpeechEntry] = field(default_factory=list)
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
