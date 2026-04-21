from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from traductor_tiempo_real.metricas.eventos import CheckResult, CheckStatus, MetricEvent


@dataclass(frozen=True, slots=True)
class AudioFrame:
    frame_id: str
    created_at: float
    sample_rate: int
    channels: int
    frame_count: int
    audio: np.ndarray
    overflowed: bool = False


@dataclass(frozen=True, slots=True)
class SpeechSegment:
    segment_id: str
    created_at: float
    started_at: float
    finished_at: float
    duration_ms: float
    closure_latency_ms: float
    sample_rate: int
    frame_count: int
    samples: np.ndarray
    energy_rms: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "segment_id": self.segment_id,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_ms": self.duration_ms,
            "closure_latency_ms": self.closure_latency_ms,
            "sample_rate": self.sample_rate,
            "frame_count": self.frame_count,
            "sample_count": int(self.samples.size),
            "energy_rms": self.energy_rms,
            "metadata": self.metadata,
        }


@dataclass(frozen=True, slots=True)
class ActiveSpeechSnapshot:
    segment_id: str
    created_at: float
    started_at: float
    updated_at: float
    duration_ms: float
    sample_rate: int
    frame_count: int
    samples: np.ndarray
    energy_rms: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "segment_id": self.segment_id,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "duration_ms": self.duration_ms,
            "sample_rate": self.sample_rate,
            "frame_count": self.frame_count,
            "sample_count": int(self.samples.size),
            "energy_rms": self.energy_rms,
            "metadata": self.metadata,
        }


@dataclass(frozen=True, slots=True)
class CaptureDiagnosticReport:
    duration_seconds: float
    device_info: dict[str, Any]
    frames_processed: int
    dropped_chunks: int
    segments: list[SpeechSegment] = field(default_factory=list)
    events: list[MetricEvent] = field(default_factory=list)
    checks: list[CheckResult] = field(default_factory=list)
    vad_score_summary: dict[str, float] = field(default_factory=dict)

    def is_successful(self) -> bool:
        return not any(check.status == CheckStatus.ERROR for check in self.checks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "duration_seconds": self.duration_seconds,
            "device_info": self.device_info,
            "frames_processed": self.frames_processed,
            "dropped_chunks": self.dropped_chunks,
            "segment_count": len(self.segments),
            "segments": [segment.to_dict() for segment in self.segments],
            "events": [event.to_dict() for event in self.events],
            "checks": [check.to_dict() for check in self.checks],
            "vad_score_summary": self.vad_score_summary,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False, default=str)
