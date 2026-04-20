from __future__ import annotations

from contextlib import contextmanager
from time import monotonic
from uuid import uuid4

from traductor_tiempo_real.metricas.eventos import EventStatus, MetricEvent


@contextmanager
def measure_stage(
    stage: str,
    *,
    collector: list[MetricEvent] | None = None,
    operation_id: str | None = None,
    metadata: dict[str, object] | None = None,
):
    started_at = monotonic()
    status = EventStatus.OK
    error: str | None = None
    try:
        yield
    except Exception as exc:
        status = EventStatus.ERROR
        error = str(exc)
        raise
    finally:
        finished_at = monotonic()
        event = MetricEvent(
            operation_id=operation_id or uuid4().hex,
            stage=stage,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=(finished_at - started_at) * 1000,
            status=status,
            metadata=dict(metadata or {}),
            error=error,
        )
        if collector is not None:
            collector.append(event)
