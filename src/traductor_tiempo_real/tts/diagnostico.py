from __future__ import annotations

import json

from traductor_tiempo_real.asr.diagnostico import VALIDATION_SCRIPTS
from traductor_tiempo_real.configuracion.modelos import AppConfig
from traductor_tiempo_real.metricas.eventos import CheckResult, CheckStatus
from traductor_tiempo_real.metricas.reporte import BenchmarkReport
from traductor_tiempo_real.metricas.tiempo import measure_stage
from traductor_tiempo_real.pipeline.bootstrap import SpeechRuntime, StartupCallback, TtsRuntime, bootstrap_speech_runtime, bootstrap_tts_runtime
from traductor_tiempo_real.traduccion.diagnostico import run_live_translation
from traductor_tiempo_real.tts.kokoro import get_voice_for_language
from traductor_tiempo_real.tts.modelos import GuidedSpeechEntry, GuidedSpeechReport, LiveSpeechReport, TtsDiagnosticReport, TtsResult
from traductor_tiempo_real.tts.servicio import TtsProcessingService


def format_tts_result_line(result: TtsResult) -> str:
    if result.status == "played":
        return f"[TTS-PLAY][{result.language}][{result.voice}][ttfa={result.time_to_first_audio_ms:.0f} ms]"
    if result.status == "skipped":
        return f"[TTS-SKIP][{result.language}] {result.skip_reason}"
    return f"[TTS-ERROR][{result.language}][{result.total_synthesis_ms:.0f} ms] {result.error}"


def run_tts_diagnostic(
    config: AppConfig,
    *,
    text: str,
    play_audio: bool = True,
    runtime: TtsRuntime | None = None,
    on_startup_step: StartupCallback | None = None,
    on_ready=None,
) -> TtsDiagnosticReport:
    own_runtime = runtime is None
    runtime = runtime or bootstrap_tts_runtime(config, on_step=on_startup_step, play_audio=play_audio)
    if on_ready is not None:
        on_ready()

    language = config.target_language.value
    voice = get_voice_for_language(language, config.tts)
    events = runtime.events
    checks = runtime.checks
    service = runtime.tts_service

    results: list[TtsResult] = []
    original_callback = service._result_callback
    service._result_callback = results.append

    with measure_stage("tts.diagnostic_request", collector=events, metadata={"language": language, "voice": voice}):
        service.speak_text(text, language=language)

    service.wait_until_drained(timeout_seconds=30.0)
    if own_runtime:
        service.close()
        service.join(timeout=30.0)
    drained = service.poll_results()
    result = results[-1] if results else drained[-1]
    service._result_callback = original_callback
    return TtsDiagnosticReport(language=language, voice=voice, text=text, result=result, events=events, checks=checks)


def render_tts_diagnostic(report: TtsDiagnosticReport) -> str:
    result = report.result
    lines = [
        "Diagnóstico TTS Sprint 4",
        f"Éxito global: {'sí' if report.is_successful() else 'no'}",
        f"Idioma: {report.language}",
        f"Voz: {report.voice or 'n/d'}",
        f"Estado: {result.status}",
        f"TTFA: {result.time_to_first_audio_ms:.1f} ms",
        f"Síntesis total: {result.total_synthesis_ms:.1f} ms",
        f"Duración audio: {result.playback_duration_ms:.1f} ms",
    ]
    return "\n".join(lines)


def run_live_speech(
    config: AppConfig,
    *,
    duration_seconds: float = 30.0,
    max_segments: int | None = None,
    play_audio: bool = True,
    on_asr_result=None,
    on_translation_result=None,
    on_tts_result=None,
    runtime: SpeechRuntime | None = None,
    on_startup_step: StartupCallback | None = None,
    on_ready=None,
) -> LiveSpeechReport:
    own_runtime = runtime is None

    def translation_callback(result):
        if on_translation_result is not None:
            on_translation_result(result)
        speech_runtime.tts.tts_service.submit_translation_result(result)

    speech_runtime = runtime or bootstrap_speech_runtime(
        config,
        on_step=on_startup_step,
        translation_result_callback=translation_callback,
        tts_result_callback=on_tts_result,
        play_audio=play_audio,
    )
    if on_ready is not None:
        on_ready()

    translation_report = run_live_translation(
        config,
        duration_seconds=duration_seconds,
        max_segments=max_segments,
        on_asr_result=on_asr_result,
        runtime=speech_runtime.translation,
    )

    tts_service = speech_runtime.tts.tts_service
    tts_events = speech_runtime.tts.events
    tts_checks = speech_runtime.tts.checks

    tts_service.wait_until_drained(timeout_seconds=30.0)
    if own_runtime:
        tts_service.close()
        tts_service.join(timeout=30.0)
        speech_runtime.translation.translation_service.close()
        speech_runtime.translation.translation_service.join(timeout=config.translation.timeout_seconds)
        speech_runtime.translation.asr.asr_service.close()
        speech_runtime.translation.asr.asr_service.join(timeout=30.0)

    tts_results = tts_service.poll_results()

    return LiveSpeechReport(
        translation_report=translation_report,
        tts_results=tts_results,
        events=tts_events,
        checks=tts_checks,
    )


def render_live_speech_summary(report: LiveSpeechReport) -> str:
    lines = [
        "Resumen de traducción con voz",
        f"Éxito global: {'sí' if report.is_successful() else 'no'}",
        f"Dispositivo: {report.translation_report.asr_report.device_info.get('name', 'desconocido')}",
        f"Finales ASR: {report.translation_report.asr_report.final_count}",
        f"Traducidas: {report.translation_report.translated_count}",
        f"TTS reproducidos: {report.played_count}",
        f"TTS omitidos: {report.skipped_count}",
        f"TTS errores: {report.error_count}",
    ]
    return "\n".join(lines)


def run_guided_speech_validation(
    config: AppConfig,
    *,
    script_name: str,
    segment_timeout: float = 8.0,
    play_audio: bool = True,
    on_asr_result=None,
    on_translation_result=None,
    on_tts_result=None,
    prompt_callback=None,
    wait_callback=None,
    on_startup_step: StartupCallback | None = None,
    on_ready=None,
) -> GuidedSpeechReport:
    prompts = VALIDATION_SCRIPTS.get(script_name)
    if prompts is None:
        raise ValueError(f"Script de validación no soportado: {script_name}")

    entries: list[GuidedSpeechEntry] = []
    checks = [
        CheckResult(
            name="tts.guided_validation.script",
            status=CheckStatus.OK,
            message="Script de validación guiada de voz cargado.",
            details={"script_name": script_name, "prompt_count": len(prompts)},
        )
    ]

    def translation_callback(result) -> None:
        if on_translation_result is not None:
            on_translation_result(result)
        runtime.tts.tts_service.submit_translation_result(result)

    runtime = bootstrap_speech_runtime(
        config,
        on_step=on_startup_step,
        translation_result_callback=translation_callback,
        tts_result_callback=on_tts_result,
        play_audio=play_audio,
    )
    if on_ready is not None:
        on_ready()

    try:
        for index, prompt in enumerate(prompts, start=1):
            if prompt_callback is not None:
                prompt_callback(index, prompt)
            if wait_callback is not None:
                wait_callback()
            report = run_live_speech(
                config,
                duration_seconds=segment_timeout,
                max_segments=1,
                play_audio=play_audio,
                on_asr_result=on_asr_result,
                runtime=runtime,
            )
            translations = report.translation_report.translations
            tts_results = report.tts_results
            entries.append(
                GuidedSpeechEntry(
                    prompt=prompt,
                    report=report,
                    translation_status=translations[-1].status if translations else "missing",
                    spoken_status=tts_results[-1].status if tts_results else "missing",
                )
            )
    finally:
        runtime.translation.asr.asr_service.close()
        runtime.translation.asr.asr_service.join(timeout=30.0)
        runtime.translation.translation_service.close()
        runtime.translation.translation_service.join(timeout=config.translation.timeout_seconds)
        runtime.tts.tts_service.close()
        runtime.tts.tts_service.join(timeout=30.0)

    return GuidedSpeechReport(script_name=script_name, entries=entries, checks=checks)


def render_guided_speech_validation(report: GuidedSpeechReport) -> str:
    lines = [f"Validación guiada de voz: {report.script_name}"]
    for index, entry in enumerate(report.entries, start=1):
        lines.append(f"{index}. Prompt: {entry.prompt}")
        lines.append(f"   Traducción: {entry.translation_status}")
        lines.append(f"   Voz: {entry.spoken_status}")
    return "\n".join(lines)


def build_tts_benchmark_cases(language: str) -> list[dict[str, str]]:
    text_by_language = {
        "en": [
            {"label": "corto", "text": "Hello, this is a short TTS test."},
            {"label": "medio", "text": "Hello, this is a medium length validation for the Kokoro TTS backend in sprint four."},
            {"label": "consecutivas", "text": "Hello, this is the first sentence. This is the second sentence for consecutive playback."},
        ],
        "es": [
            {"label": "corto", "text": "Hola, esta es una prueba corta de voz."},
            {"label": "medio", "text": "Hola, esta es una validación de longitud media para el backend Kokoro del sprint cuatro."},
            {"label": "consecutivas", "text": "Hola, esta es la primera frase. Esta es la segunda frase para probar reproducción consecutiva."},
        ],
        "fr": [
            {"label": "corto", "text": "Bonjour, ceci est un court test de synthèse."},
            {"label": "medio", "text": "Bonjour, ceci est une validation de longueur moyenne pour le backend Kokoro du sprint quatre."},
            {"label": "consecutivas", "text": "Bonjour, ceci est la première phrase. Ceci est la deuxième phrase pour la lecture consécutive."},
        ],
        "it": [
            {"label": "corto", "text": "Ciao, questo è un breve test vocale."},
            {"label": "medio", "text": "Ciao, questa è una validazione di media lunghezza per il backend Kokoro dello sprint quattro."},
            {"label": "consecutivas", "text": "Ciao, questa è la prima frase. Questa è la seconda frase per la riproduzione consecutiva."},
        ],
    }
    return text_by_language.get(language.lower(), [])


def run_tts_benchmark(config: AppConfig, *, play_audio: bool = False) -> BenchmarkReport:
    events = []
    checks = []
    language = config.target_language.value
    voice = get_voice_for_language(language, config.tts)
    if voice is None:
        raise ValueError(f"No hay voz Kokoro configurada para el idioma {language}")

    results = []
    cases = build_tts_benchmark_cases(language)
    for case in cases:
        with measure_stage(
            "tts.benchmark_request",
            collector=events,
            metadata={"label": case['label'], "language": language, "voice": voice},
        ):
            report = run_tts_diagnostic(config, text=case["text"], play_audio=play_audio)
        result = report.result
        results.append(
            {
                "label": case["label"],
                "language": language,
                "voice": voice,
                "text": case["text"],
                "status": result.status,
                "time_to_first_audio_ms": result.time_to_first_audio_ms,
                "total_synthesis_ms": result.total_synthesis_ms,
                "playback_duration_ms": result.playback_duration_ms,
                "play_audio": play_audio,
            }
        )

    checks.append(
        CheckResult(
            name="tts.benchmark.voice",
            status=CheckStatus.OK,
            message="Benchmark TTS ejecutado con voz configurada.",
            details={"language": language, "voice": voice},
        )
    )

    return BenchmarkReport(
        name="benchmark_tts_sprint_4",
        environment={"project_root": str(config.project_root)},
        configuration={
            "backend": config.tts.backend,
            "language": language,
            "voice": voice,
            "play_audio": play_audio,
        },
        events=events,
        checks=checks,
        notes=[json.dumps(item, ensure_ascii=False) for item in results],
    )


def render_tts_benchmark(report: BenchmarkReport) -> str:
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
