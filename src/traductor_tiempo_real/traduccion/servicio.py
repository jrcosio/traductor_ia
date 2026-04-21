from __future__ import annotations

from collections import deque
from queue import Empty, SimpleQueue
from threading import Condition, Thread
from time import monotonic, sleep
from uuid import uuid4

from traductor_tiempo_real.asr.modelos import AsrResult
from traductor_tiempo_real.configuracion.modelos import TranslationConfig
from traductor_tiempo_real.metricas.eventos import CheckResult, CheckStatus, MetricEvent
from traductor_tiempo_real.metricas.tiempo import measure_stage
from traductor_tiempo_real.traduccion.modelos import TranslationRequest, TranslationResult
from traductor_tiempo_real.traduccion.ollama import OllamaTranslationBackend


class _TranslationTaskQueue:
    def __init__(self) -> None:
        self._pending: deque[TranslationRequest] = deque()
        self._closed = False
        self._condition = Condition()

    @property
    def is_empty(self) -> bool:
        with self._condition:
            return not self._pending

    def submit(self, request: TranslationRequest) -> None:
        with self._condition:
            if self._closed:
                raise RuntimeError("La cola de traducción ya está cerrada")
            self._pending.append(request)
            self._condition.notify()

    def get(self, timeout: float = 0.1) -> TranslationRequest | None:
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


class TranslationProcessingService:
    def __init__(
        self,
        config: TranslationConfig,
        *,
        collector: list[MetricEvent] | None = None,
        checks: list[CheckResult] | None = None,
        backend: OllamaTranslationBackend | None = None,
        result_callback=None,
    ) -> None:
        self._config = config
        self._collector = collector if collector is not None else []
        self._checks = checks if checks is not None else []
        self._backend = backend or OllamaTranslationBackend(config)
        self._result_callback = result_callback
        self._tasks = _TranslationTaskQueue()
        self._results: SimpleQueue[TranslationResult] = SimpleQueue()
        self._worker: Thread | None = None

    def start(self) -> "TranslationProcessingService":
        if self._worker is not None:
            return self

        with measure_stage(
            "translation.backend_init",
            collector=self._collector,
            metadata={"backend": self._config.backend, "model": self._config.preferred_model},
        ):
            self._checks.append(
                CheckResult(
                    name="translation.backend",
                    status=CheckStatus.OK,
                    message="Backend de traducción inicializado.",
                    details={"backend": self._config.backend, "model": self._config.preferred_model},
                )
            )

        if self._config.warmup_on_start:
            with measure_stage("translation.warmup", collector=self._collector):
                self._backend.warmup()
                self._checks.append(
                    CheckResult(
                        name="translation.warmup",
                        status=CheckStatus.OK,
                        message="Warmup del modelo de traducción completado.",
                    )
                )

        self._worker = Thread(target=self._run, name="translation-worker", daemon=True)
        self._worker.start()
        return self

    def submit_asr_result(self, asr_result: AsrResult, *, target_language: str) -> None:
        if not asr_result.is_final:
            return

        if asr_result.error:
            self._emit_result(
                TranslationResult(
                    request_id=uuid4().hex,
                    utterance_id=asr_result.utterance_id,
                    status="error",
                    text="",
                    source_text=asr_result.text,
                    source_language=asr_result.language,
                    target_language=target_language,
                    created_at=monotonic(),
                    started_at=monotonic(),
                    finished_at=monotonic(),
                    latency_ms=0.0,
                    model=self._config.preferred_model,
                    metadata=asr_result.metadata,
                    error=asr_result.error,
                )
            )
            return

        source_text = asr_result.text.strip()
        source_language = (asr_result.language or "").lower() or None
        target_language = target_language.lower()

        if not source_text:
            self._emit_result(
                TranslationResult(
                    request_id=uuid4().hex,
                    utterance_id=asr_result.utterance_id,
                    status="skipped",
                    text="",
                    source_text=source_text,
                    source_language=source_language,
                    target_language=target_language,
                    created_at=monotonic(),
                    started_at=monotonic(),
                    finished_at=monotonic(),
                    latency_ms=0.0,
                    model=self._config.preferred_model,
                    metadata=asr_result.metadata,
                    skip_reason="empty_source_text",
                )
            )
            return

        if source_language == target_language:
            self._emit_result(
                TranslationResult(
                    request_id=uuid4().hex,
                    utterance_id=asr_result.utterance_id,
                    status="skipped",
                    text="",
                    source_text=source_text,
                    source_language=source_language,
                    target_language=target_language,
                    created_at=monotonic(),
                    started_at=monotonic(),
                    finished_at=monotonic(),
                    latency_ms=0.0,
                    model=self._config.preferred_model,
                    metadata=asr_result.metadata,
                    skip_reason="source_equals_target",
                )
            )
            return

        self._tasks.submit(
            TranslationRequest(
                request_id=uuid4().hex,
                utterance_id=asr_result.utterance_id,
                created_at=monotonic(),
                source_text=source_text,
                source_language=source_language,
                target_language=target_language,
                is_final=True,
                metadata=asr_result.metadata,
            )
        )

    def poll_results(self) -> list[TranslationResult]:
        drained: list[TranslationResult] = []
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

    def wait_until_drained(self, timeout_seconds: float = 30.0) -> None:
        deadline = monotonic() + timeout_seconds
        while monotonic() < deadline:
            if self._tasks.is_empty:
                return
            sleep(0.02)
        raise TimeoutError("La cola de traducción no se vació dentro del tiempo esperado")

    def _emit_result(self, result: TranslationResult) -> None:
        self._results.put(result)
        if self._result_callback is not None:
            self._result_callback(result)

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
                    "translation.generate",
                    collector=self._collector,
                    operation_id=request.request_id,
                    metadata={
                        "utterance_id": request.utterance_id,
                        "target_language": request.target_language,
                    },
                ):
                    translated_text, metadata = self._backend.translate(
                        request.source_text,
                        source_language=request.source_language,
                        target_language=request.target_language,
                    )
                finished_at = monotonic()
                result = TranslationResult(
                    request_id=request.request_id,
                    utterance_id=request.utterance_id,
                    status="translated",
                    text=translated_text,
                    source_text=request.source_text,
                    source_language=request.source_language,
                    target_language=request.target_language,
                    created_at=request.created_at,
                    started_at=started_at,
                    finished_at=finished_at,
                    latency_ms=(finished_at - started_at) * 1000,
                    model=self._config.preferred_model,
                    metadata={**request.metadata, **metadata},
                )
            except Exception as exc:
                finished_at = monotonic()
                result = TranslationResult(
                    request_id=request.request_id,
                    utterance_id=request.utterance_id,
                    status="error",
                    text="",
                    source_text=request.source_text,
                    source_language=request.source_language,
                    target_language=request.target_language,
                    created_at=request.created_at,
                    started_at=started_at,
                    finished_at=finished_at,
                    latency_ms=(finished_at - started_at) * 1000,
                    model=self._config.preferred_model,
                    metadata=request.metadata,
                    error=str(exc),
                )

            self._emit_result(result)
