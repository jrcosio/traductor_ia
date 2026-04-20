from __future__ import annotations

from statistics import fmean
from time import monotonic

from traductor_tiempo_real.audio.captura import MicrophoneCapture, probe_default_input_device
from traductor_tiempo_real.audio.modelos import CaptureDiagnosticReport
from traductor_tiempo_real.configuracion.modelos import AppConfig
from traductor_tiempo_real.metricas.eventos import CheckResult, CheckStatus
from traductor_tiempo_real.metricas.tiempo import measure_stage
from traductor_tiempo_real.vad.segmentador import SpeechSegmenter
from traductor_tiempo_real.vad.silero import SileroSpeechDetector


def run_capture_diagnostic(
    config: AppConfig,
    *,
    duration_seconds: float = 10.0,
    max_segments: int | None = None,
) -> CaptureDiagnosticReport:
    if duration_seconds <= 0:
        raise ValueError("duration_seconds debe ser mayor que cero")

    events = []
    checks = []
    segments = []
    scores: list[float] = []

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
                details={"window_ms": config.vad.window_ms, "threshold": config.vad.threshold},
            )
        )

    segmenter = SpeechSegmenter(config.audio, config.vad)
    frames_processed = 0
    deadline = monotonic() + duration_seconds
    capture = MicrophoneCapture(config.audio)

    with measure_stage("audio.capture_session", collector=events, metadata={"duration_seconds": duration_seconds}):
        with capture:
            while monotonic() < deadline:
                frame = capture.read_frame(timeout=0.5)
                if frame is None:
                    continue
                frames_processed += 1
                with measure_stage("vad.score", collector=events):
                    is_speech, score = detector.is_speech(frame.audio, frame.sample_rate)
                scores.append(score)
                segments.extend(segmenter.process_frame(frame, is_speech=is_speech, score=score))
                if max_segments is not None and len(segments) >= max_segments:
                    break

            segments.extend(segmenter.flush())

    checks.append(
        CheckResult(
            name="audio.capture.frames",
            status=CheckStatus.OK,
            message="Sesión de captura completada.",
            details={
                "frames_processed": frames_processed,
                "dropped_chunks": capture.dropped_chunks,
                "segment_count": len(segments),
                "status_messages": list(capture.status_messages),
            },
        )
    )

    if scores:
        vad_score_summary = {
            "min": min(scores),
            "max": max(scores),
            "avg": fmean(scores),
        }
    else:
        vad_score_summary = {}

    return CaptureDiagnosticReport(
        duration_seconds=duration_seconds,
        device_info=device_info,
        frames_processed=frames_processed,
        dropped_chunks=capture.dropped_chunks,
        segments=segments,
        events=events,
        checks=checks,
        vad_score_summary=vad_score_summary,
    )


def render_capture_diagnostic(report: CaptureDiagnosticReport) -> str:
    lines = [
        "Diagnóstico de captura Sprint 1",
        f"Éxito global: {'sí' if report.is_successful() else 'no'}",
        f"Dispositivo: {report.device_info.get('name', 'desconocido')}",
        f"Frames procesados: {report.frames_processed}",
        f"Chunks descartados: {report.dropped_chunks}",
        f"Segmentos detectados: {len(report.segments)}",
    ]

    if report.vad_score_summary:
        lines.append(
            "Puntuación VAD: "
            f"min={report.vad_score_summary['min']:.4f} "
            f"max={report.vad_score_summary['max']:.4f} "
            f"avg={report.vad_score_summary['avg']:.4f}"
        )

    lines.append("")
    lines.append("Checks:")
    for check in report.checks:
        lines.append(f"- [{check.status}] {check.name}: {check.message}")

    if report.segments:
        lines.append("")
        lines.append("Segmentos:")
        for segment in report.segments:
            lines.append(
                "- "
                f"{segment.segment_id[:8]} "
                f"duración={segment.duration_ms:.1f} ms "
                f"cierre={segment.closure_latency_ms:.1f} ms "
                f"energía={segment.energy_rms:.4f} "
                f"razón={segment.metadata.get('reason', 'n/d')}"
            )

    return "\n".join(lines)
