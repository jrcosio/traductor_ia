from __future__ import annotations

import json
from pathlib import Path
from time import monotonic
from typing import Callable
import wave

import numpy as np

from traductor_tiempo_real.asr.modelos import GuidedValidationEntry, GuidedValidationReport, LiveTranscriptionReport, AsrResult
from traductor_tiempo_real.asr.servicio import AsrProcessingService
from traductor_tiempo_real.asr.whisper_mlx import MlxWhisperBackend
from traductor_tiempo_real.audio.captura import MicrophoneCapture, probe_default_input_device
from traductor_tiempo_real.benchmark_base import inspect_sample
from traductor_tiempo_real.configuracion.modelos import AppConfig
from traductor_tiempo_real.metricas.eventos import CheckResult, CheckStatus
from traductor_tiempo_real.metricas.reporte import BenchmarkReport
from traductor_tiempo_real.metricas.tiempo import measure_stage
from traductor_tiempo_real.vad.segmentador import SpeechSegmenter
from traductor_tiempo_real.vad.silero import SileroSpeechDetector


VALIDATION_SCRIPTS: dict[str, tuple[str, ...]] = {
    "es-basico": (
        "Hola, esto es una prueba de transcripción en tiempo real.",
        "Estoy validando el segundo sprint del proyecto.",
    ),
    "en-basico": (
        "Hello, this is a real time transcription test.",
        "I am validating the second sprint of the project.",
    ),
    "mixto-corto": (
        "Hola, esta es una prueba rápida.",
        "This is a short English validation.",
    ),
}


def format_asr_result_line(result: AsrResult) -> str:
    kind = "FINAL" if result.is_final else "PARCIAL"
    language = result.language or "?"
    if result.error:
        return f"[{kind}][error][{result.latency_ms:.0f} ms] {result.error}"
    return f"[{kind}][{language}][{result.latency_ms:.0f} ms] {result.text}"


def _drain_results(
    service: AsrProcessingService,
    *,
    results: list[AsrResult],
    on_result: Callable[[AsrResult], None] | None,
    language_history: dict[str, list[str]],
    emitted_partial_texts: dict[str, str],
) -> None:
    for result in service.poll_results():
        if not result.is_final:
            previous_partial = emitted_partial_texts.get(result.utterance_id)
            if previous_partial == result.text:
                continue
            emitted_partial_texts[result.utterance_id] = result.text
        if result.language:
            language_history.setdefault(result.utterance_id, []).append(result.language)
        results.append(result)
        if on_result is not None:
            on_result(result)


def _compute_language_stability(results: list[AsrResult]) -> dict[str, dict[str, object]]:
    grouped: dict[str, list[AsrResult]] = {}
    for result in results:
        grouped.setdefault(result.utterance_id, []).append(result)

    stability: dict[str, dict[str, object]] = {}
    for utterance_id, utterance_results in grouped.items():
        final = next((item for item in reversed(utterance_results) if item.is_final), None)
        languages = [item.language for item in utterance_results if item.language]
        if final is None:
            continue
        matches_final = sum(1 for language in languages if language == final.language)
        stability[utterance_id] = {
            "final_language": final.language,
            "observed_languages": languages,
            "stability_ratio": (matches_final / len(languages)) if languages else 0.0,
        }
    return stability


def run_live_transcription(
    config: AppConfig,
    *,
    duration_seconds: float = 30.0,
    max_segments: int | None = None,
    enable_partials: bool | None = None,
    on_result: Callable[[AsrResult], None] | None = None,
) -> LiveTranscriptionReport:
    if duration_seconds <= 0:
        raise ValueError("duration_seconds debe ser mayor que cero")

    allow_partials = config.asr.enable_partials if enable_partials is None else enable_partials
    events = []
    checks = []
    results: list[AsrResult] = []
    emitted_partial_texts: dict[str, str] = {}
    language_history: dict[str, list[str]] = {}

    with measure_stage("audio.device_probe", collector=events):
        device_info = probe_default_input_device()
        checks.append(
            CheckResult(
                name="audio.default_device",
                status=CheckStatus.OK,
                message="Dispositivo de entrada por defecto accesible.",
                details={"name": device_info["name"], "sample_rate": device_info["default_samplerate"]},
            )
        )

    with measure_stage("vad.load", collector=events):
        detector = SileroSpeechDetector(config.vad)
        checks.append(
            CheckResult(
                name="vad.silero.load",
                status=CheckStatus.OK,
                message="Silero VAD cargado correctamente.",
            )
        )

    service = AsrProcessingService(config.asr, collector=events, checks=checks).start()
    segmenter = SpeechSegmenter(config.audio, config.vad)
    capture = MicrophoneCapture(config.audio)
    frames_processed = 0
    completed_segments = 0
    next_partial_deadline = 0.0
    active_partial_segment_id: str | None = None
    deadline = monotonic() + duration_seconds

    with measure_stage("audio.asr_live_session", collector=events, metadata={"duration_seconds": duration_seconds}):
        with capture:
            while monotonic() < deadline:
                frame = capture.read_frame(timeout=0.2)
                _drain_results(
                    service,
                    results=results,
                    on_result=on_result,
                    language_history=language_history,
                    emitted_partial_texts=emitted_partial_texts,
                )
                if frame is None:
                    continue

                frames_processed += 1
                with measure_stage("vad.score", collector=events):
                    is_speech, score = detector.is_speech(frame.audio, frame.sample_rate)

                final_segments = segmenter.process_frame(frame, is_speech=is_speech, score=score)
                for segment in final_segments:
                    service.submit_final(segment)
                    completed_segments += 1
                    active_partial_segment_id = None
                    if max_segments is not None and completed_segments >= max_segments:
                        deadline = 0.0
                        break

                if allow_partials and segmenter.is_active:
                    snapshot = segmenter.snapshot()
                    now = monotonic()
                    if snapshot is not None:
                        if snapshot.segment_id != active_partial_segment_id:
                            active_partial_segment_id = snapshot.segment_id
                            next_partial_deadline = now
                        if snapshot.duration_ms >= config.asr.min_partial_ms and now >= next_partial_deadline:
                            service.submit_partial(snapshot)
                            next_partial_deadline = now + (config.asr.partial_interval_ms / 1000)

            for segment in segmenter.flush():
                service.submit_final(segment)

    service.wait_until_drained(timeout_seconds=30.0)
    service.close()
    service.join(timeout=30.0)
    _drain_results(
        service,
        results=results,
        on_result=on_result,
        language_history=language_history,
        emitted_partial_texts=emitted_partial_texts,
    )

    checks.append(
        CheckResult(
            name="audio.asr_live.frames",
            status=CheckStatus.OK,
            message="Sesión de captura y transcripción completada.",
            details={
                "frames_processed": frames_processed,
                "dropped_chunks": capture.dropped_chunks,
                "partial_count": sum(1 for result in results if not result.is_final),
                "final_count": sum(1 for result in results if result.is_final),
            },
        )
    )

    return LiveTranscriptionReport(
        duration_seconds=duration_seconds,
        device_info=device_info,
        frames_processed=frames_processed,
        dropped_chunks=capture.dropped_chunks,
        results=results,
        events=events,
        checks=checks,
        language_stability=_compute_language_stability(results),
    )


def render_live_transcription_summary(report: LiveTranscriptionReport) -> str:
    lines = [
        "Resumen de transcripción en vivo",
        f"Éxito global: {'sí' if report.is_successful() else 'no'}",
        f"Dispositivo: {report.device_info.get('name', 'desconocido')}",
        f"Frames procesados: {report.frames_processed}",
        f"Parciales: {report.partial_count}",
        f"Finales: {report.final_count}",
        f"Chunks descartados: {report.dropped_chunks}",
    ]
    if report.language_stability:
        lines.append("")
        lines.append("Estabilidad de idioma:")
        for utterance_id, info in report.language_stability.items():
            lines.append(
                f"- {utterance_id[:8]} final={info['final_language']} estabilidad={info['stability_ratio']:.2f}"
            )
    return "\n".join(lines)


def run_guided_validation(
    config: AppConfig,
    *,
    script_name: str,
    segment_timeout: float = 8.0,
    on_result: Callable[[AsrResult], None] | None = None,
    prompt_callback: Callable[[int, str], None] | None = None,
    wait_callback: Callable[[], None] | None = None,
) -> GuidedValidationReport:
    prompts = VALIDATION_SCRIPTS.get(script_name)
    if prompts is None:
        raise ValueError(f"Script de validación no soportado: {script_name}")

    entries: list[GuidedValidationEntry] = []
    checks = [
        CheckResult(
            name="asr.guided_validation.script",
            status=CheckStatus.OK,
            message="Script de validación cargado.",
            details={"script_name": script_name, "prompt_count": len(prompts)},
        )
    ]

    for index, prompt in enumerate(prompts, start=1):
        if prompt_callback is not None:
            prompt_callback(index, prompt)
        if wait_callback is not None:
            wait_callback()

        report = run_live_transcription(
            config,
            duration_seconds=segment_timeout,
            max_segments=1,
            enable_partials=False,
            on_result=on_result,
        )
        finals = [result for result in report.results if result.is_final and result.text]
        final = finals[-1] if finals else None
        entries.append(
            GuidedValidationEntry(
                prompt=prompt,
                report=report,
                final_text=final.text if final else "",
                detected_language=final.language if final else None,
            )
        )

    return GuidedValidationReport(script_name=script_name, entries=entries, checks=checks)


def render_guided_validation(report: GuidedValidationReport) -> str:
    lines = [f"Validación guiada: {report.script_name}"]
    for index, entry in enumerate(report.entries, start=1):
        lines.append(f"{index}. Prompt: {entry.prompt}")
        lines.append(f"   Texto final: {entry.final_text or '[vacío]'}")
        lines.append(f"   Idioma detectado: {entry.detected_language or '?'}")
    return "\n".join(lines)


def load_wav_mono(sample_path: Path) -> tuple[np.ndarray, int]:
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
    return audio, sample_rate


def run_asr_benchmark(config: AppConfig, sample_paths: list[Path]) -> BenchmarkReport:
    events = []
    checks = []
    if not sample_paths:
        raise ValueError("No se proporcionaron muestras WAV para benchmark ASR")

    transcriptions = []
    with measure_stage(
        "asr.benchmark_backend_init",
        collector=events,
        metadata={"backend": config.asr.backend, "model_repo": config.asr.model_repo},
    ):
        backend_impl = MlxWhisperBackend(config.asr)
        checks.append(
            CheckResult(
                name="asr.benchmark.backend",
                status=CheckStatus.OK,
                message="Backend ASR de benchmark inicializado.",
                details={"backend": config.asr.backend, "model_repo": config.asr.model_repo},
            )
        )

    with measure_stage("asr.benchmark_warmup", collector=events):
        backend_impl.warmup()
        checks.append(
            CheckResult(
                name="asr.benchmark.warmup",
                status=CheckStatus.OK,
                message="Warmup de benchmark ASR completado.",
            )
        )

    for sample_path in sample_paths:
        sample_check, sample_metadata = inspect_sample(sample_path)
        checks.append(sample_check)
        audio, sample_rate = load_wav_mono(sample_path)
        started_at = monotonic()
        with measure_stage(
            "asr.benchmark_transcribe",
            collector=events,
            metadata={"sample": str(sample_path)},
        ):
            text, language, metadata = backend_impl.transcribe(audio, sample_rate=sample_rate)
        latency_ms = (monotonic() - started_at) * 1000
        transcriptions.append(
            {
                "sample": str(sample_path),
                "language": language,
                "text": text,
                "latency_ms": latency_ms,
                "duration_ms": sample_metadata.get("duration_ms"),
                **metadata,
            }
        )

    return BenchmarkReport(
        name="benchmark_asr_sprint_2",
        environment={"project_root": str(config.project_root)},
        configuration={
            "backend": config.asr.backend,
            "model_repo": config.asr.model_repo,
        },
        events=events,
        checks=checks,
        notes=[json.dumps(item, ensure_ascii=False) for item in transcriptions],
    )


def render_asr_benchmark(report: BenchmarkReport) -> str:
    lines = [
        f"Benchmark: {report.name}",
        f"Éxito global: {'sí' if report.is_successful() else 'no'}",
        "",
        "Checks:",
    ]
    for check in report.checks:
        lines.append(f"- [{check.status}] {check.name}: {check.message}")
    lines.append("")
    lines.append("Resultados:")
    lines.extend(f"- {note}" for note in report.notes)
    return "\n".join(lines)
