from __future__ import annotations

from collections import deque
from queue import Empty, SimpleQueue
from threading import Condition, Thread
from time import monotonic, sleep
from uuid import uuid4

from traductor_tiempo_real.configuracion.modelos import TtsConfig
from traductor_tiempo_real.metricas.eventos import CheckResult, CheckStatus, MetricEvent
from traductor_tiempo_real.metricas.tiempo import measure_stage
from traductor_tiempo_real.traduccion.modelos import TranslationResult
from traductor_tiempo_real.tts.kokoro import KokoroTtsBackend, get_voice_for_language
from traductor_tiempo_real.tts.modelos import TtsRequest, TtsResult
from traductor_tiempo_real.tts.reproductor import SoundDeviceAudioPlayer


class _TtsTaskQueue:
    def __init__(self) -> None:
        self._pending: deque[TtsRequest] = deque()
        self._closed = False
        self._condition = Condition()

    @property
    def is_empty(self) -> bool:
        with self._condition:
            return not self._pending

    def submit(self, request: TtsRequest) -> None:
        with self._condition:
            if self._closed:
                raise RuntimeError("La cola TTS ya está cerrada")
            self._pending.append(request)
            self._condition.notify()

    def get(self, timeout: float = 0.1) -> TtsRequest | None:
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


class TtsProcessingService:
    def __init__(
        self,
        config: TtsConfig,
        *,
        target_language: str,
        collector: list[MetricEvent] | None = None,
        checks: list[CheckResult] | None = None,
        backend: KokoroTtsBackend | None = None,
        player: SoundDeviceAudioPlayer | None = None,
        result_callback=None,
        play_audio: bool = True,
    ) -> None:
        self._config = config
        self._target_language = target_language.lower()
        self._collector = collector if collector is not None else []
        self._checks = checks if checks is not None else []
        self._backend = backend or KokoroTtsBackend(config)
        self._player = player or SoundDeviceAudioPlayer(config)
        self._result_callback = result_callback
        self._play_audio = play_audio
        self._tasks = _TtsTaskQueue()
        self._results: SimpleQueue[TtsResult] = SimpleQueue()
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
            "tts.backend_init",
            collector=self._collector,
            metadata={"backend": self._config.backend, "target_language": self._target_language},
        ):
            self._checks.append(
                CheckResult(
                    name="tts.backend",
                    status=CheckStatus.OK,
                    message="Backend TTS inicializado.",
                    details={"backend": self._config.backend, "target_language": self._target_language},
                )
            )
        self._backend_initialized = True

    def warmup(self) -> None:
        self.initialize_backend()
        if self._warmed_up or not self._config.warmup_on_start or not self._backend.supports_language(self._target_language):
            return

        with measure_stage("tts.warmup", collector=self._collector):
            self._backend.warmup(self._target_language)
            self._checks.append(
                CheckResult(
                    name="tts.warmup",
                    status=CheckStatus.OK,
                    message="Warmup del backend TTS completado.",
                )
            )
        self._warmed_up = True

    def start(self) -> "TtsProcessingService":
        if self._worker is not None:
            return self

        self.warmup()

        self._worker = Thread(target=self._run, name="tts-worker", daemon=True)
        self._worker.start()
        return self

    def submit_translation_result(self, result: TranslationResult) -> None:
        if result.status == "translated":
            text = result.text.strip()
            language = result.target_language.lower()
        elif result.status == "skipped" and result.skip_reason == "source_equals_target":
            text = result.source_text.strip()
            language = result.target_language.lower()
        else:
            self._emit_result(
                TtsResult(
                    request_id=uuid4().hex,
                    utterance_id=result.utterance_id,
                    status="skipped",
                    language=result.target_language.lower(),
                    voice=get_voice_for_language(result.target_language.lower(), self._config),
                    text=result.text or result.source_text,
                    created_at=monotonic(),
                    started_at=monotonic(),
                    finished_at=monotonic(),
                    time_to_first_audio_ms=0.0,
                    total_synthesis_ms=0.0,
                    playback_duration_ms=0.0,
                    sample_rate=self._config.sample_rate,
                    metadata=result.metadata,
                    skip_reason=result.skip_reason or result.status,
                )
            )
            return

        if not text:
            self._emit_result(
                TtsResult(
                    request_id=uuid4().hex,
                    utterance_id=result.utterance_id,
                    status="skipped",
                    language=language,
                    voice=get_voice_for_language(language, self._config),
                    text=text,
                    created_at=monotonic(),
                    started_at=monotonic(),
                    finished_at=monotonic(),
                    time_to_first_audio_ms=0.0,
                    total_synthesis_ms=0.0,
                    playback_duration_ms=0.0,
                    sample_rate=self._config.sample_rate,
                    metadata=result.metadata,
                    skip_reason="empty_text",
                )
            )
            return

        voice = get_voice_for_language(language, self._config)
        if voice is None:
            self._emit_result(
                TtsResult(
                    request_id=uuid4().hex,
                    utterance_id=result.utterance_id,
                    status="skipped",
                    language=language,
                    voice=None,
                    text=text,
                    created_at=monotonic(),
                    started_at=monotonic(),
                    finished_at=monotonic(),
                    time_to_first_audio_ms=0.0,
                    total_synthesis_ms=0.0,
                    playback_duration_ms=0.0,
                    sample_rate=self._config.sample_rate,
                    metadata=result.metadata,
                    skip_reason="unsupported_language",
                )
            )
            return

        request = TtsRequest(
            request_id=uuid4().hex,
            utterance_id=result.utterance_id,
            created_at=monotonic(),
            text=text,
            language=language,
            voice=voice,
            source_status=result.status,
            metadata=result.metadata,
        )
        self._register_task()
        try:
            self._tasks.submit(request)
        except Exception:
            self._complete_task()
            raise

    def speak_text(self, text: str, *, language: str) -> None:
        voice = get_voice_for_language(language.lower(), self._config)
        request = TtsRequest(
            request_id=uuid4().hex,
            utterance_id=uuid4().hex,
            created_at=monotonic(),
            text=text,
            language=language.lower(),
            voice=voice,
            source_status="direct",
        )
        self._register_task()
        try:
            self._tasks.submit(request)
        except Exception:
            self._complete_task()
            raise

    def poll_results(self) -> list[TtsResult]:
        drained: list[TtsResult] = []
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
        with self._state_condition:
            while self._unfinished_tasks > 0:
                remaining = deadline - monotonic()
                if remaining <= 0:
                    raise TimeoutError("La cola TTS no se vació dentro del tiempo esperado")
                self._state_condition.wait(timeout=remaining)

    def _emit_result(self, result: TtsResult) -> None:
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
                first_chunk_at: float | None = None

                def measured_chunks():
                    nonlocal first_chunk_at
                    for chunk in self._backend.synthesize(request.text, language=request.language):
                        if first_chunk_at is None:
                            first_chunk_at = monotonic()
                        yield chunk

                with measure_stage(
                    "tts.synthesize_play",
                    collector=self._collector,
                    operation_id=request.request_id,
                    metadata={"language": request.language, "voice": request.voice},
                ):
                    playback = self._player.play_chunks(
                        measured_chunks(),
                        sample_rate=self._config.sample_rate,
                        play_audio=self._play_audio,
                    )

                finished_at = monotonic()
                ttfa_ms = ((first_chunk_at - started_at) * 1000) if first_chunk_at is not None else 0.0
                result = TtsResult(
                    request_id=request.request_id,
                    utterance_id=request.utterance_id,
                    status="played",
                    language=request.language,
                    voice=request.voice,
                    text=request.text,
                    created_at=request.created_at,
                    started_at=started_at,
                    finished_at=finished_at,
                    time_to_first_audio_ms=ttfa_ms,
                    total_synthesis_ms=(finished_at - started_at) * 1000,
                    playback_duration_ms=playback["audio_duration_ms"],
                    sample_rate=self._config.sample_rate,
                    metadata={**request.metadata, **playback, "play_audio": self._play_audio},
                )
            except Exception as exc:
                finished_at = monotonic()
                result = TtsResult(
                    request_id=request.request_id,
                    utterance_id=request.utterance_id,
                    status="error",
                    language=request.language,
                    voice=request.voice,
                    text=request.text,
                    created_at=request.created_at,
                    started_at=started_at,
                    finished_at=finished_at,
                    time_to_first_audio_ms=0.0,
                    total_synthesis_ms=(finished_at - started_at) * 1000,
                    playback_duration_ms=0.0,
                    sample_rate=self._config.sample_rate,
                    metadata=request.metadata,
                    error=str(exc),
                )

            self._emit_result(result)
            self._complete_task()
