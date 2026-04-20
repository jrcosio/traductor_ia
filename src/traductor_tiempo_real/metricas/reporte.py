from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from traductor_tiempo_real.metricas.eventos import CheckResult, CheckStatus, MetricEvent


@dataclass(frozen=True, slots=True)
class BenchmarkReport:
    name: str
    environment: dict[str, Any]
    configuration: dict[str, Any]
    events: list[MetricEvent] = field(default_factory=list)
    checks: list[CheckResult] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "generated_at": self.generated_at,
            "environment": self.environment,
            "configuration": self.configuration,
            "events": [event.to_dict() for event in self.events],
            "checks": [check.to_dict() for check in self.checks],
            "notes": list(self.notes),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False, default=str)

    def is_successful(self) -> bool:
        return not any(check.status == CheckStatus.ERROR for check in self.checks)
