from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from traductor_tiempo_real.asr.modelos import AsrResult
from traductor_tiempo_real.metricas.estadisticas import latency_summary
from traductor_tiempo_real.metricas.eventos import CheckResult, CheckStatus
from traductor_tiempo_real.traduccion.modelos import TranslationResult
from traductor_tiempo_real.tts.modelos import TtsResult


@dataclass(frozen=True, slots=True)
class PipelineEvent:
    event_id: str
    session_id: str
    stage: str
    kind: str
    created_at: float
    utterance_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "session_id": self.session_id,
            "stage": self.stage,
            "kind": self.kind,
            "created_at": self.created_at,
            "utterance_id": self.utterance_id,
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class QueueStats:
    maxsizes: dict[str, int]
    high_watermarks: dict[str, int] = field(default_factory=dict)
    dropped: dict[str, int] = field(default_factory=dict)

    def record_qsize(self, name: str, qsize: int) -> None:
        current = self.high_watermarks.get(name, 0)
        if qsize > current:
            self.high_watermarks[name] = qsize

    def record_drop(self, name: str) -> None:
        self.dropped[name] = self.dropped.get(name, 0) + 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "maxsizes": dict(self.maxsizes),
            "high_watermarks": dict(self.high_watermarks),
            "dropped": dict(self.dropped),
        }


@dataclass(slots=True)
class UtteranceTrace:
    utterance_id: str
    target_language: str
    segment_started_at: float | None = None
    segment_finished_at: float | None = None
    segment_emitted_at: float | None = None
    asr_started_at: float | None = None
    asr_finished_at: float | None = None
    translation_started_at: float | None = None
    translation_finished_at: float | None = None
    tts_started_at: float | None = None
    tts_first_audio_at: float | None = None
    tts_finished_at: float | None = None
    source_language: str | None = None
    asr_text: str = ""
    translation_status: str | None = None
    translation_text: str = ""
    tts_status: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "utterance_id": self.utterance_id,
            "target_language": self.target_language,
            "segment_started_at": self.segment_started_at,
            "segment_finished_at": self.segment_finished_at,
            "segment_emitted_at": self.segment_emitted_at,
            "asr_started_at": self.asr_started_at,
            "asr_finished_at": self.asr_finished_at,
            "translation_started_at": self.translation_started_at,
            "translation_finished_at": self.translation_finished_at,
            "tts_started_at": self.tts_started_at,
            "tts_first_audio_at": self.tts_first_audio_at,
            "tts_finished_at": self.tts_finished_at,
            "source_language": self.source_language,
            "asr_text": self.asr_text,
            "translation_status": self.translation_status,
            "translation_text": self.translation_text,
            "tts_status": self.tts_status,
            "end_to_end_to_translation_ms": self._duration_ms(self.segment_started_at, self.translation_finished_at),
            "end_to_end_to_first_audio_ms": self._duration_ms(self.segment_started_at, self.tts_first_audio_at),
        }

    @staticmethod
    def _duration_ms(start: float | None, end: float | None) -> float | None:
        if start is None or end is None:
            return None
        return (end - start) * 1000


@dataclass(frozen=True, slots=True)
class PipelineReport:
    session_id: str
    target_language: str
    input_device: dict[str, Any]
    output_device: dict[str, Any] | None
    frames_processed: int
    segments_emitted: int
    duration_seconds: float
    asr_results: list[AsrResult] = field(default_factory=list)
    translation_results: list[TranslationResult] = field(default_factory=list)
    tts_results: list[TtsResult] = field(default_factory=list)
    events: list[PipelineEvent] = field(default_factory=list)
    checks: list[CheckResult] = field(default_factory=list)
    queue_stats: QueueStats = field(default_factory=lambda: QueueStats(maxsizes={}))
    utterance_metrics: dict[str, UtteranceTrace] = field(default_factory=dict)
    cpu_time_seconds: float = 0.0
    max_rss_mb: float = 0.0

    def is_successful(self) -> bool:
        return not any(check.status == CheckStatus.ERROR for check in self.checks)

    def latency_summary(self) -> dict[str, dict[str, float | int | None]]:
        traces = [trace.to_dict() for trace in self.utterance_metrics.values()]
        translation_latencies = [
            value
            for value in (trace["end_to_end_to_translation_ms"] for trace in traces)
            if value is not None
        ]
        first_audio_latencies = [
            value
            for value in (trace["end_to_end_to_first_audio_ms"] for trace in traces)
            if value is not None
        ]
        return {
            "end_to_end_to_translation": latency_summary(translation_latencies),
            "end_to_end_to_first_audio": latency_summary(first_audio_latencies),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "target_language": self.target_language,
            "input_device": self.input_device,
            "output_device": self.output_device,
            "frames_processed": self.frames_processed,
            "segments_emitted": self.segments_emitted,
            "duration_seconds": self.duration_seconds,
            "asr_results": [item.to_dict() for item in self.asr_results],
            "translation_results": [item.to_dict() for item in self.translation_results],
            "tts_results": [item.to_dict() for item in self.tts_results],
            "events": [item.to_dict() for item in self.events],
            "checks": [item.to_dict() for item in self.checks],
            "queue_stats": self.queue_stats.to_dict(),
            "utterance_metrics": {key: value.to_dict() for key, value in self.utterance_metrics.items()},
            "latency_summary": self.latency_summary(),
            "cpu_time_seconds": self.cpu_time_seconds,
            "max_rss_mb": self.max_rss_mb,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False, default=str)
