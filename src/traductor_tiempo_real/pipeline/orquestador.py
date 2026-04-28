from __future__ import annotations

import asyncio
import resource
import sys
from time import monotonic, process_time
from uuid import uuid4
import wave

import numpy as np

from traductor_tiempo_real.audio.captura import MicrophoneCapture
from traductor_tiempo_real.audio.modelos import SpeechSegment
from traductor_tiempo_real.configuracion.modelos import AppConfig
from traductor_tiempo_real.metricas.eventos import CheckResult, CheckStatus
from traductor_tiempo_real.pipeline.bootstrap import StartupCallback, bootstrap_speech_runtime
from traductor_tiempo_real.pipeline.modelos import PipelineEvent, PipelineReport, QueueStats, UtteranceTrace
from traductor_tiempo_real.vad.segmentador import SpeechSegmenter


_SENTINEL = object()


def _max_rss_mb() -> float:
    maxrss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        return maxrss / (1024 * 1024)
    return maxrss / 1024


def _load_wav_as_segment(sample_path, target_language: str) -> SpeechSegment:
    with wave.open(str(sample_path), "rb") as wav_file:
        sample_rate = wav_file.getframerate()
        sample_width = wav_file.getsampwidth()
        channels = wav_file.getnchannels()
        frames = wav_file.readframes(wav_file.getnframes())

    if sample_width != 2:
        raise ValueError(f"Solo se soportan WAV PCM de 16 bits, recibido sample_width={sample_width}")

    audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)

    started_at = monotonic()
    finished_at = started_at + (audio.size / sample_rate)
    return SpeechSegment(
        segment_id=uuid4().hex,
        created_at=finished_at,
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=(audio.size / sample_rate) * 1000,
        closure_latency_ms=0.0,
        sample_rate=sample_rate,
        frame_count=max(1, int(audio.size / 512)),
        samples=audio,
        energy_rms=float(np.sqrt(np.mean(np.square(audio)))) if audio.size else 0.0,
        metadata={"source": "pre_recorded", "target_language": target_language},
    )


class _PipelineCollector:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.events: list[PipelineEvent] = []
        self.checks: list[CheckResult] = []
        self.asr_results = []
        self.translation_results = []
        self.tts_results = []
        self.utterance_metrics: dict[str, UtteranceTrace] = {}
        self.queue_stats = QueueStats(
            maxsizes={
                "segments": config.pipeline.segments_queue_max_items,
                "translation": config.pipeline.translation_queue_max_items,
                "tts": config.pipeline.tts_queue_max_items,
                "events": config.pipeline.event_queue_max_items,
            }
        )
        self.frames_processed = 0
        self.segments_emitted = 0
        self._event_drop_count = 0

    def ensure_trace(self, utterance_id: str) -> UtteranceTrace:
        if utterance_id not in self.utterance_metrics:
            self.utterance_metrics[utterance_id] = UtteranceTrace(
                utterance_id=utterance_id,
                target_language=self.config.target_language.value,
            )
        return self.utterance_metrics[utterance_id]

    def add_check(self, name: str, status: CheckStatus, message: str, *, details=None) -> None:
        self.checks.append(CheckResult(name=name, status=status, message=message, details=details or {}))


async def _safe_emit_event(events_queue: asyncio.Queue, collector: _PipelineCollector, *, session_id: str, stage: str, kind: str, utterance_id: str | None = None, metadata=None) -> None:
    event = PipelineEvent(
        event_id=uuid4().hex,
        session_id=session_id,
        stage=stage,
        kind=kind,
        created_at=monotonic(),
        utterance_id=utterance_id,
        metadata=dict(metadata or {}),
    )
    try:
        events_queue.put_nowait(event)
        collector.queue_stats.record_qsize("events", events_queue.qsize())
    except asyncio.QueueFull:
        collector.queue_stats.record_drop("events")


async def _event_sink(events_queue: asyncio.Queue, collector: _PipelineCollector) -> None:
    while True:
        event = await events_queue.get()
        if event is _SENTINEL:
            break
        collector.events.append(event)


async def _put_with_backpressure(queue: asyncio.Queue, *, queue_name: str, item, collector: _PipelineCollector, session_id: str, stage: str, events_queue: asyncio.Queue, utterance_id: str | None = None, metadata=None) -> bool:
    try:
        queue.put_nowait(item)
        collector.queue_stats.record_qsize(queue_name, queue.qsize())
        return True
    except asyncio.QueueFull:
        collector.queue_stats.record_drop(queue_name)
        collector.add_check(
            f"pipeline.queue.{queue_name}",
            CheckStatus.WARNING,
            f"Cola {queue_name} saturada; elemento descartado.",
            details={"queue": queue_name},
        )
        await _safe_emit_event(
            events_queue,
            collector,
            session_id=session_id,
            stage=stage,
            kind="queue_drop",
            utterance_id=utterance_id,
            metadata={"queue": queue_name, **(metadata or {})},
        )
        return False


async def _produce_live_segments(config: AppConfig, runtime, collector: _PipelineCollector, session_id: str, segments_queue: asyncio.Queue, events_queue: asyncio.Queue, *, duration_seconds: float, max_segments: int | None) -> None:
    detector = runtime.translation.asr.detector
    segmenter = SpeechSegmenter(config.audio, config.vad)
    emitted = 0
    deadline = monotonic() + duration_seconds
    with MicrophoneCapture(config.audio) as capture:
        while monotonic() < deadline:
            frame = await asyncio.to_thread(capture.read_frame, 0.2)
            if frame is None:
                continue
            collector.frames_processed += 1
            is_speech, score = detector.is_speech(frame.audio, frame.sample_rate)
            for segment in segmenter.process_frame(frame, is_speech=is_speech, score=score):
                collector.segments_emitted += 1
                emitted += 1
                trace = collector.ensure_trace(segment.segment_id)
                trace.segment_started_at = segment.started_at
                trace.segment_finished_at = segment.finished_at
                trace.segment_emitted_at = segment.created_at
                await _safe_emit_event(
                    events_queue,
                    collector,
                    session_id=session_id,
                    stage="segment",
                    kind="segment_emitted",
                    utterance_id=segment.segment_id,
                    metadata={"duration_ms": segment.duration_ms},
                )
                await _put_with_backpressure(
                    segments_queue,
                    queue_name="segments",
                    item=segment,
                    collector=collector,
                    session_id=session_id,
                    stage="segment",
                    events_queue=events_queue,
                    utterance_id=segment.segment_id,
                    metadata={"duration_ms": segment.duration_ms},
                )
                if max_segments is not None and emitted >= max_segments:
                    deadline = 0.0
                    break
        for segment in segmenter.flush():
            collector.segments_emitted += 1
            trace = collector.ensure_trace(segment.segment_id)
            trace.segment_started_at = segment.started_at
            trace.segment_finished_at = segment.finished_at
            trace.segment_emitted_at = segment.created_at
            await _safe_emit_event(
                events_queue,
                collector,
                session_id=session_id,
                stage="segment",
                kind="segment_emitted",
                utterance_id=segment.segment_id,
                metadata={"duration_ms": segment.duration_ms, "reason": "flush"},
            )
            await _put_with_backpressure(
                segments_queue,
                queue_name="segments",
                item=segment,
                collector=collector,
                session_id=session_id,
                stage="segment",
                events_queue=events_queue,
                utterance_id=segment.segment_id,
                metadata={"duration_ms": segment.duration_ms, "reason": "flush"},
            )
    await segments_queue.put(_SENTINEL)


async def _produce_pre_recorded_segments(sample_paths, collector: _PipelineCollector, session_id: str, segments_queue: asyncio.Queue, events_queue: asyncio.Queue, *, target_language: str) -> None:
    for sample_path in sample_paths:
        segment = _load_wav_as_segment(sample_path, target_language)
        collector.segments_emitted += 1
        trace = collector.ensure_trace(segment.segment_id)
        trace.segment_started_at = segment.started_at
        trace.segment_finished_at = segment.finished_at
        trace.segment_emitted_at = segment.created_at
        await _safe_emit_event(
            events_queue,
            collector,
            session_id=session_id,
            stage="segment",
            kind="segment_emitted",
            utterance_id=segment.segment_id,
            metadata={"sample": str(sample_path), "duration_ms": segment.duration_ms},
        )
        await _put_with_backpressure(
            segments_queue,
            queue_name="segments",
            item=segment,
            collector=collector,
            session_id=session_id,
            stage="segment",
            events_queue=events_queue,
            utterance_id=segment.segment_id,
            metadata={"sample": str(sample_path), "duration_ms": segment.duration_ms},
        )
    await segments_queue.put(_SENTINEL)


async def _dispatch_segments(runtime, segments_queue: asyncio.Queue, done_event: asyncio.Event) -> None:
    while True:
        item = await segments_queue.get()
        if item is _SENTINEL:
            break
        runtime.translation.asr.asr_service.submit_final(item)
    await asyncio.to_thread(runtime.translation.asr.asr_service.wait_until_drained, 30.0)
    done_event.set()


async def _collect_asr_results(config: AppConfig, runtime, translation_queue: asyncio.Queue, events_queue: asyncio.Queue, collector: _PipelineCollector, session_id: str, submit_done: asyncio.Event, on_asr_result=None) -> None:
    service = runtime.translation.asr.asr_service
    poll_interval = config.pipeline.dispatch_poll_interval_ms / 1000
    while True:
        drained = service.poll_results()
        for result in drained:
            collector.asr_results.append(result)
            trace = collector.ensure_trace(result.utterance_id)
            trace.asr_started_at = result.started_at
            trace.asr_finished_at = result.finished_at
            trace.source_language = result.language
            trace.asr_text = result.text
            await _safe_emit_event(
                events_queue,
                collector,
                session_id=session_id,
                stage="asr",
                kind="asr_final" if result.is_final else "asr_partial",
                utterance_id=result.utterance_id,
                metadata={"language": result.language, "latency_ms": result.latency_ms},
            )
            if on_asr_result is not None:
                on_asr_result(result)
            if result.is_final:
                await _put_with_backpressure(
                    translation_queue,
                    queue_name="translation",
                    item=result,
                    collector=collector,
                    session_id=session_id,
                    stage="translation",
                    events_queue=events_queue,
                    utterance_id=result.utterance_id,
                    metadata={"language": result.language},
                )
        if submit_done.is_set() and service.unfinished_tasks == 0 and drained == []:
            break
        await asyncio.sleep(poll_interval)
    await translation_queue.put(_SENTINEL)


async def _dispatch_translation(config: AppConfig, runtime, translation_queue: asyncio.Queue, done_event: asyncio.Event) -> None:
    while True:
        item = await translation_queue.get()
        if item is _SENTINEL:
            break
        runtime.translation.translation_service.submit_asr_result(item, target_language=config.target_language.value)
    await asyncio.to_thread(runtime.translation.translation_service.wait_until_drained, config.translation.timeout_seconds)
    done_event.set()


async def _collect_translation_results(config: AppConfig, runtime, tts_queue: asyncio.Queue, events_queue: asyncio.Queue, collector: _PipelineCollector, session_id: str, submit_done: asyncio.Event, on_translation_result=None) -> None:
    service = runtime.translation.translation_service
    poll_interval = config.pipeline.dispatch_poll_interval_ms / 1000
    while True:
        drained = service.poll_results()
        for result in drained:
            collector.translation_results.append(result)
            trace = collector.ensure_trace(result.utterance_id)
            trace.translation_started_at = result.started_at
            trace.translation_finished_at = result.finished_at
            trace.translation_status = result.status
            trace.translation_text = result.text
            await _safe_emit_event(
                events_queue,
                collector,
                session_id=session_id,
                stage="translation",
                kind=f"translation_{result.status}",
                utterance_id=result.utterance_id,
                metadata={"latency_ms": result.latency_ms, "target_language": result.target_language},
            )
            if on_translation_result is not None:
                on_translation_result(result)
            await _put_with_backpressure(
                tts_queue,
                queue_name="tts",
                item=result,
                collector=collector,
                session_id=session_id,
                stage="tts",
                events_queue=events_queue,
                utterance_id=result.utterance_id,
                metadata={"status": result.status},
            )
        if submit_done.is_set() and service.unfinished_tasks == 0 and drained == []:
            break
        await asyncio.sleep(poll_interval)
    await tts_queue.put(_SENTINEL)


async def _dispatch_tts(runtime, tts_queue: asyncio.Queue, done_event: asyncio.Event) -> None:
    while True:
        item = await tts_queue.get()
        if item is _SENTINEL:
            break
        runtime.tts.tts_service.submit_translation_result(item)
    await asyncio.to_thread(runtime.tts.tts_service.wait_until_drained, 30.0)
    done_event.set()


async def _collect_tts_results(runtime, events_queue: asyncio.Queue, collector: _PipelineCollector, session_id: str, submit_done: asyncio.Event, on_tts_result=None) -> None:
    service = runtime.tts.tts_service
    while True:
        drained = service.poll_results()
        for result in drained:
            collector.tts_results.append(result)
            trace = collector.ensure_trace(result.utterance_id)
            trace.tts_started_at = result.started_at
            trace.tts_finished_at = result.finished_at
            trace.tts_status = result.status
            if result.status == "played" and result.time_to_first_audio_ms:
                trace.tts_first_audio_at = result.started_at + (result.time_to_first_audio_ms / 1000)
            await _safe_emit_event(
                events_queue,
                collector,
                session_id=session_id,
                stage="tts",
                kind=f"tts_{result.status}",
                utterance_id=result.utterance_id,
                metadata={"voice": result.voice, "ttfa_ms": result.time_to_first_audio_ms},
            )
            if on_tts_result is not None:
                on_tts_result(result)
        if submit_done.is_set() and service.unfinished_tasks == 0 and drained == []:
            break
        await asyncio.sleep(0.02)


async def _run_pipeline_async(
    config: AppConfig,
    *,
    runtime,
    duration_seconds: float,
    max_segments: int | None,
    play_audio: bool,
    on_asr_result=None,
    on_translation_result=None,
    on_tts_result=None,
    sample_paths=None,
) -> PipelineReport:
    collector = _PipelineCollector(config)
    session_id = uuid4().hex
    events_queue: asyncio.Queue = asyncio.Queue(maxsize=config.pipeline.event_queue_max_items)
    segments_queue: asyncio.Queue = asyncio.Queue(maxsize=config.pipeline.segments_queue_max_items)
    translation_queue: asyncio.Queue = asyncio.Queue(maxsize=config.pipeline.translation_queue_max_items)
    tts_queue: asyncio.Queue = asyncio.Queue(maxsize=config.pipeline.tts_queue_max_items)
    asr_submit_done = asyncio.Event()
    translation_submit_done = asyncio.Event()
    tts_submit_done = asyncio.Event()

    cpu_start = process_time()
    wall_start = monotonic()

    await _safe_emit_event(events_queue, collector, session_id=session_id, stage="session", kind="session_started", metadata={"target_language": config.target_language.value})

    tasks = [asyncio.create_task(_event_sink(events_queue, collector))]

    if sample_paths is None:
        tasks.append(asyncio.create_task(_produce_live_segments(config, runtime, collector, session_id, segments_queue, events_queue, duration_seconds=duration_seconds, max_segments=max_segments)))
    else:
        tasks.append(asyncio.create_task(_produce_pre_recorded_segments(sample_paths, collector, session_id, segments_queue, events_queue, target_language=config.target_language.value)))

    tasks.extend(
        [
            asyncio.create_task(_dispatch_segments(runtime, segments_queue, asr_submit_done)),
            asyncio.create_task(_collect_asr_results(config, runtime, translation_queue, events_queue, collector, session_id, asr_submit_done, on_asr_result=on_asr_result)),
            asyncio.create_task(_dispatch_translation(config, runtime, translation_queue, translation_submit_done)),
            asyncio.create_task(_collect_translation_results(config, runtime, tts_queue, events_queue, collector, session_id, translation_submit_done, on_translation_result=on_translation_result)),
            asyncio.create_task(_dispatch_tts(runtime, tts_queue, tts_submit_done)),
            asyncio.create_task(_collect_tts_results(runtime, events_queue, collector, session_id, tts_submit_done, on_tts_result=on_tts_result)),
        ]
    )

    try:
        await asyncio.gather(*tasks[1:])
        await _safe_emit_event(events_queue, collector, session_id=session_id, stage="session", kind="session_finished")
    finally:
        await events_queue.put(_SENTINEL)
        await tasks[0]
        runtime.translation.asr.asr_service.close()
        runtime.translation.asr.asr_service.join(timeout=30.0)
        runtime.translation.translation_service.close()
        runtime.translation.translation_service.join(timeout=config.translation.timeout_seconds)
        runtime.tts.tts_service.close()
        runtime.tts.tts_service.join(timeout=30.0)

    cpu_elapsed = process_time() - cpu_start
    duration = monotonic() - wall_start
    return PipelineReport(
        session_id=session_id,
        target_language=config.target_language.value,
        input_device=runtime.translation.asr.device_info,
        output_device=runtime.tts.output_device_info,
        frames_processed=collector.frames_processed,
        segments_emitted=collector.segments_emitted,
        duration_seconds=duration,
        asr_results=collector.asr_results,
        translation_results=collector.translation_results,
        tts_results=collector.tts_results,
        events=collector.events,
        checks=collector.checks,
        queue_stats=collector.queue_stats,
        utterance_metrics=collector.utterance_metrics,
        cpu_time_seconds=cpu_elapsed,
        max_rss_mb=_max_rss_mb(),
    )


def run_live_pipeline(
    config: AppConfig,
    *,
    duration_seconds: float = 30.0,
    max_segments: int | None = None,
    play_audio: bool = True,
    on_startup_step: StartupCallback | None = None,
    on_ready=None,
    on_asr_result=None,
    on_translation_result=None,
    on_tts_result=None,
) -> PipelineReport:
    runtime = bootstrap_speech_runtime(config, on_step=on_startup_step, play_audio=play_audio)
    if on_ready is not None:
        on_ready()
    return asyncio.run(
        _run_pipeline_async(
            config,
            runtime=runtime,
            duration_seconds=duration_seconds,
            max_segments=max_segments,
            play_audio=play_audio,
            on_asr_result=on_asr_result,
            on_translation_result=on_translation_result,
            on_tts_result=on_tts_result,
        )
    )


def run_pre_recorded_pipeline(
    config: AppConfig,
    *,
    sample_paths,
    play_audio: bool = False,
) -> PipelineReport:
    runtime = bootstrap_speech_runtime(config, play_audio=play_audio)
    return asyncio.run(
        _run_pipeline_async(
            config,
            runtime=runtime,
            duration_seconds=0.0,
            max_segments=None,
            play_audio=play_audio,
            sample_paths=list(sample_paths),
        )
    )


def render_pipeline_summary(report: PipelineReport) -> str:
    lines = [
        "Resumen del pipeline",
        f"Sesión: {report.session_id[:8]}",
        f"Éxito global: {'sí' if report.is_successful() else 'no'}",
        f"Segmentos emitidos: {report.segments_emitted}",
        f"Finales ASR: {sum(1 for item in report.asr_results if item.is_final)}",
        f"Traducciones: {len(report.translation_results)}",
        f"TTS: {len(report.tts_results)}",
        f"CPU (s): {report.cpu_time_seconds:.3f}",
        f"RSS máx (MB): {report.max_rss_mb:.1f}",
        f"Queue highs: {report.queue_stats.high_watermarks}",
        f"Queue drops: {report.queue_stats.dropped}",
    ]
    if report.utterance_metrics:
        lines.append("")
        lines.append("Resumen de latencias:")
        for name, summary in report.latency_summary().items():
            lines.append(
                f"- {name}: n={summary['count']} p50={summary['p50_ms']} ms p95={summary['p95_ms']} ms p99={summary['p99_ms']} ms"
            )
        lines.append("")
        lines.append("Métricas end-to-end:")
        for utterance_id, trace in report.utterance_metrics.items():
            data = trace.to_dict()
            lines.append(
                f"- {utterance_id[:8]} trans={data['end_to_end_to_translation_ms']} ms first_audio={data['end_to_end_to_first_audio_ms']} ms"
            )
    return "\n".join(lines)
