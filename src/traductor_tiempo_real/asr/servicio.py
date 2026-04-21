from __future__ import annotations

from collections import deque
from queue import Empty, SimpleQueue
from threading import Condition, Thread
from time import monotonic, sleep
from uuid import uuid4

from traductor_tiempo_real.audio.modelos import ActiveSpeechSnapshot, SpeechSegment
from traductor_tiempo_real.asr.modelos import AsrRequest, AsrResult
from traductor_tiempo_real.asr.whisper_mlx import MlxWhisperBackend
from traductor_tiempo_real.configuracion.modelos import AsrConfig
from traductor_tiempo_real.metricas.eventos import CheckResult, CheckStatus, MetricEvent
from traductor_tiempo_real.metricas.tiempo import measure_stage


class _AsrTaskQueue:
    def __init__(self) -> None:
        self._pending: deque[AsrRequest] = deque()
        self._closed = False
        self._condition = Condition()

    @property
    def is_empty(self) -> bool:
        with self._condition:
            return not self._pending

    def submit(self, request: AsrRequest) -> None:
        with self._condition:
            if self._closed:
                raise RuntimeError("La cola ASR ya está cerrada")
            if request.is_final:
                self._pending.append(request)
            else:
                replaced = False
                for index, existing in enumerate(self._pending):
                    if not existing.is_final and existing.utterance_id == request.utterance_id:
                        self._pending[index] = request
                        replaced = True
                        break
                if not replaced:
                    self._pending.append(request)
            self._condition.notify()

    def get(self, timeout: float = 0.1) -> AsrRequest | None:
        with self._condition:
            if not self._pending and not self._closed:
                self._condition.wait(timeout=timeout)
            if self._pending:
                return self._pending.popleft()
            return None

    def close(self) -> None:
        with self._condition:
            self._closed = True
            self._condition.notify_all()

    def can_finish(self) -> bool:
        with self._condition:
            return self._closed and not self._pending


class AsrProcessingService:
    def __init__(
        self,
        config: AsrConfig,
        *,
        collector: list[MetricEvent] | None = None,
        checks: list[CheckResult] | None = None,
        backend: MlxWhisperBackend | None = None,
    ) -> None:
        self._config = config
        self._collector = collector if collector is not None else []
        self._checks = checks if checks is not None else []
        self._backend = backend or MlxWhisperBackend(config)
        self._tasks = _AsrTaskQueue()
        self._results: SimpleQueue[AsrResult] = SimpleQueue()
        self._worker: Thread | None = None
        self._backend_initialized = False
        self._warmed_up = False
        self._unfinished_tasks = 0
        self._state_condition = Condition()

    def _register_task(self) -> None:
        with self._state_condition:
            self._unfinished_tasks += 1

    def _complete_task(self) -> None:
        with self._state_condition:
            self._unfinished_tasks -= 1
            self._state_condition.notify_all()

    @property
    def unfinished_tasks(self) -> int:
        with self._state_condition:
            return self._unfinished_tasks

    def initialize_backend(self) -> None:
        if self._backend_initialized:
            return

        with measure_stage(
            "asr.backend_init",
            collector=self._collector,
            metadata={"backend": self._config.backend, "model_repo": self._config.model_repo},
        ):
            self._checks.append(
                CheckResult(
                    name="asr.backend",
                    status=CheckStatus.OK,
                    message="Backend ASR inicializado.",
                    details={"backend": self._config.backend, "model_repo": self._config.model_repo},
                )
            )
        self._backend_initialized = True

    def warmup(self) -> None:
        self.initialize_backend()
        if self._warmed_up or not self._config.warmup_on_start:
            return

        with measure_stage("asr.warmup", collector=self._collector):
            self._backend.warmup()
            self._checks.append(
                CheckResult(
                    name="asr.warmup",
                    status=CheckStatus.OK,
                    message="Warmup del modelo ASR completado.",
                )
            )
        self._warmed_up = True

    def start(self) -> "AsrProcessingService":
        if self._worker is not None:
            return self

        self.warmup()

        self._worker = Thread(target=self._run, name="asr-worker", daemon=True)
        self._worker.start()
        return self

    def submit_partial(self, snapshot: ActiveSpeechSnapshot) -> None:
        request = AsrRequest(
            request_id=uuid4().hex,
            utterance_id=snapshot.segment_id,
            created_at=monotonic(),
            started_at=snapshot.started_at,
            sample_rate=snapshot.sample_rate,
            duration_ms=snapshot.duration_ms,
            audio=snapshot.samples,
            is_final=False,
            metadata={"energy_rms": snapshot.energy_rms, **snapshot.metadata},
        )
        self._register_task()
        try:
            self._tasks.submit(request)
        except Exception:
            self._complete_task()
            raise

    def submit_final(self, segment: SpeechSegment) -> None:
        request = AsrRequest(
            request_id=uuid4().hex,
            utterance_id=segment.segment_id,
            created_at=monotonic(),
            started_at=segment.started_at,
            sample_rate=segment.sample_rate,
            duration_ms=segment.duration_ms,
            audio=segment.samples,
            is_final=True,
            metadata={"closure_latency_ms": segment.closure_latency_ms, **segment.metadata},
        )
        self._register_task()
        try:
            self._tasks.submit(request)
        except Exception:
            self._complete_task()
            raise

    def poll_results(self) -> list[AsrResult]:
        drained: list[AsrResult] = []
        while True:
            try:
                drained.append(self._results.get_nowait())
            except Empty:
                return drained

    def close(self) -> None:
        self._tasks.close()

    def join(self, timeout: float | None = None) -> None:
        if self._worker is not None:
            self._worker.join(timeout=timeout)

    def wait_until_drained(self, timeout_seconds: float = 15.0) -> None:
        deadline = monotonic() + timeout_seconds
        with self._state_condition:
            while self._unfinished_tasks > 0:
                remaining = deadline - monotonic()
                if remaining <= 0:
                    raise TimeoutError("La cola ASR no se vació dentro del tiempo esperado")
                self._state_condition.wait(timeout=remaining)

    def _run(self) -> None:
        while True:
            request = self._tasks.get(timeout=0.1)
            if request is None:
                if self._tasks.can_finish():
                    return
                continue

            started_at = monotonic()
            try:
                with measure_stage(
                    "asr.transcribe",
                    collector=self._collector,
                    operation_id=request.request_id,
                    metadata={
                        "utterance_id": request.utterance_id,
                        "is_final": request.is_final,
                        "duration_ms": request.duration_ms,
                    },
                ):
                    text, language, backend_metadata = self._backend.transcribe(
                        request.audio,
                        sample_rate=request.sample_rate,
                    )
                result = AsrResult(
                    request_id=request.request_id,
                    utterance_id=request.utterance_id,
                    is_final=request.is_final,
                    text=text,
                    language=language,
                    created_at=request.created_at,
                    started_at=started_at,
                    finished_at=monotonic(),
                    latency_ms=(monotonic() - started_at) * 1000,
                    source_duration_ms=request.duration_ms,
                    metadata={**request.metadata, **backend_metadata},
                )
            except Exception as exc:
                finished_at = monotonic()
                result = AsrResult(
                    request_id=request.request_id,
                    utterance_id=request.utterance_id,
                    is_final=request.is_final,
                    text="",
                    language=None,
                    created_at=request.created_at,
                    started_at=started_at,
                    finished_at=finished_at,
                    latency_ms=(finished_at - started_at) * 1000,
                    source_duration_ms=request.duration_ms,
                    metadata=request.metadata,
                    error=str(exc),
                )
            self._results.put(result)
            self._complete_task()
