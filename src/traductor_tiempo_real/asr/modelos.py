from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from traductor_tiempo_real.metricas.eventos import CheckResult, CheckStatus, MetricEvent


@dataclass(frozen=True, slots=True)
class AsrRequest:
    request_id: str
    utterance_id: str
    created_at: float
    started_at: float
    sample_rate: int
    duration_ms: float
    audio: np.ndarray
    is_final: bool
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AsrResult:
    request_id: str
    utterance_id: str
    is_final: bool
    text: str
    language: str | None
    created_at: float
    started_at: float
    finished_at: float
    latency_ms: float
    source_duration_ms: float
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def is_successful(self) -> bool:
        return self.error is None

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "utterance_id": self.utterance_id,
            "is_final": self.is_final,
            "text": self.text,
            "language": self.language,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "latency_ms": self.latency_ms,
            "source_duration_ms": self.source_duration_ms,
            "metadata": self.metadata,
            "error": self.error,
        }


@dataclass(frozen=True, slots=True)
class LiveTranscriptionReport:
    duration_seconds: float
    device_info: dict[str, Any]
    frames_processed: int
    dropped_chunks: int
    results: list[AsrResult] = field(default_factory=list)
    events: list[MetricEvent] = field(default_factory=list)
    checks: list[CheckResult] = field(default_factory=list)
    language_stability: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def partial_count(self) -> int:
        return sum(1 for result in self.results if not result.is_final)

    @property
    def final_count(self) -> int:
        return sum(1 for result in self.results if result.is_final)

    def is_successful(self) -> bool:
        return not any(check.status == CheckStatus.ERROR for check in self.checks) and all(
            result.is_successful() for result in self.results
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "duration_seconds": self.duration_seconds,
            "device_info": self.device_info,
            "frames_processed": self.frames_processed,
            "dropped_chunks": self.dropped_chunks,
            "partial_count": self.partial_count,
            "final_count": self.final_count,
            "results": [result.to_dict() for result in self.results],
            "events": [event.to_dict() for event in self.events],
            "checks": [check.to_dict() for check in self.checks],
            "language_stability": self.language_stability,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False, default=str)


@dataclass(frozen=True, slots=True)
class GuidedValidationEntry:
    prompt: str
    report: LiveTranscriptionReport
    final_text: str
    detected_language: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "prompt": self.prompt,
            "final_text": self.final_text,
            "detected_language": self.detected_language,
            "report": self.report.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class GuidedValidationReport:
    script_name: str
    entries: list[GuidedValidationEntry] = field(default_factory=list)
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
