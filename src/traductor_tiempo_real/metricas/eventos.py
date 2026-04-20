from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class EventStatus(StrEnum):
    OK = "ok"
    ERROR = "error"


class CheckStatus(StrEnum):
    OK = "ok"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class MetricEvent:
    operation_id: str
    stage: str
    started_at: float
    finished_at: float
    duration_ms: float
    status: EventStatus
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "stage": self.stage,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_ms": self.duration_ms,
            "status": self.status.value,
            "metadata": self.metadata,
            "error": self.error,
        }


@dataclass(frozen=True, slots=True)
class CheckResult:
    name: str
    status: CheckStatus
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "details": self.details,
        }
