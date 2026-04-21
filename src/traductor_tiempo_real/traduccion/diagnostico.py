from __future__ import annotations

import json

from traductor_tiempo_real.asr.diagnostico import VALIDATION_SCRIPTS, format_asr_result_line, run_live_transcription
from traductor_tiempo_real.asr.modelos import AsrResult
from traductor_tiempo_real.configuracion.modelos import AppConfig
from traductor_tiempo_real.metricas.eventos import CheckResult, CheckStatus
from traductor_tiempo_real.metricas.reporte import BenchmarkReport
from traductor_tiempo_real.metricas.tiempo import measure_stage
from traductor_tiempo_real.pipeline.bootstrap import StartupCallback, TranslationRuntime, bootstrap_translation_runtime
from traductor_tiempo_real.traduccion.modelos import GuidedTranslationEntry, GuidedTranslationReport, LiveTranslationReport, TranslationResult
from traductor_tiempo_real.traduccion.servicio import TranslationProcessingService


def format_translation_result_line(result: TranslationResult) -> str:
    if result.status == "translated":
        return f"[TRAD-FINAL][{result.target_language}][{result.latency_ms:.0f} ms] {result.text}"
    if result.status == "skipped":
        return f"[TRAD-SKIP][{result.target_language}] omitida: {result.skip_reason}"
    return f"[TRAD-ERROR][{result.target_language}][{result.latency_ms:.0f} ms] {result.error}"


def build_translation_benchmark_cases(target_language: str) -> list[dict[str, str]]:
    target_language = target_language.lower()
    if target_language == "en":
        source_language = "es"
        cases = [
            {"label": "3_palabras", "text": "Hola, esto funciona"},
            {"label": "8_palabras", "text": "Hola, esto es una prueba corta de traducción."},
            {
                "label": "15_palabras",
                "text": "Hola, esto es una validación del sprint tres para medir latencia y limpieza de salida.",
            },
        ]
    else:
        source_language = "en"
        cases = [
            {"label": "3_palabras", "text": "Hello, this works"},
            {"label": "8_palabras", "text": "Hello, this is a short translation benchmark today."},
            {
                "label": "15_palabras",
                "text": "Hello, this is a realistic sprint three validation to measure latency and output cleanliness today.",
            },
        ]

    return [{"source_language": source_language, **case} for case in cases]


def run_live_translation(
    config: AppConfig,
    *,
    duration_seconds: float = 30.0,
    max_segments: int | None = None,
    on_asr_result=None,
    on_translation_result=None,
    runtime: TranslationRuntime | None = None,
    on_startup_step: StartupCallback | None = None,
    on_ready=None,
) -> LiveTranslationReport:
    own_runtime = runtime is None
    runtime = runtime or bootstrap_translation_runtime(
        config,
        on_step=on_startup_step,
        result_callback=on_translation_result,
    )
    if on_ready is not None:
        on_ready()

    translation_service = runtime.translation_service
    translation_events = runtime.events
    translation_checks = runtime.checks

    def handle_asr_result(result: AsrResult) -> None:
        if result.is_final:
            if on_asr_result is not None:
                on_asr_result(result)
            translation_service.submit_asr_result(result, target_language=config.target_language.value)

    asr_report = run_live_transcription(
        config,
        duration_seconds=duration_seconds,
        max_segments=max_segments,
        enable_partials=False,
        on_result=handle_asr_result,
        runtime=runtime.asr,
    )

    translation_service.wait_until_drained(timeout_seconds=config.translation.timeout_seconds)
    if own_runtime:
        translation_service.close()
        translation_service.join(timeout=config.translation.timeout_seconds)
        runtime.asr.asr_service.close()
        runtime.asr.asr_service.join(timeout=30.0)

    translation_results: list[TranslationResult] = []
    for result in translation_service.poll_results():
        if result not in translation_results:
            translation_results.append(result)

    return LiveTranslationReport(
        asr_report=asr_report,
        translations=translation_results,
        events=translation_events,
        checks=translation_checks,
    )


def render_live_translation_summary(report: LiveTranslationReport) -> str:
    lines = [
        "Resumen de traducción en vivo",
        f"Éxito global: {'sí' if report.is_successful() else 'no'}",
        f"Dispositivo: {report.asr_report.device_info.get('name', 'desconocido')}",
        f"Frames procesados: {report.asr_report.frames_processed}",
        f"Finales ASR: {report.asr_report.final_count}",
        f"Traducidas: {report.translated_count}",
        f"Omitidas: {report.skipped_count}",
        f"Errores: {report.error_count}",
    ]
    return "\n".join(lines)


def run_guided_translation_validation(
    config: AppConfig,
    *,
    script_name: str,
    segment_timeout: float = 8.0,
    on_asr_result=None,
    on_translation_result=None,
    prompt_callback=None,
    wait_callback=None,
    on_startup_step: StartupCallback | None = None,
    on_ready=None,
) -> GuidedTranslationReport:
    prompts = VALIDATION_SCRIPTS.get(script_name)
    if prompts is None:
        raise ValueError(f"Script de validación no soportado: {script_name}")

    entries: list[GuidedTranslationEntry] = []
    checks = [
        CheckResult(
            name="translation.guided_validation.script",
            status=CheckStatus.OK,
            message="Script de validación de traducción cargado.",
            details={"script_name": script_name, "prompt_count": len(prompts)},
        )
    ]

    runtime = bootstrap_translation_runtime(
        config,
        on_step=on_startup_step,
        result_callback=on_translation_result,
    )
    if on_ready is not None:
        on_ready()

    try:
        for index, prompt in enumerate(prompts, start=1):
            if prompt_callback is not None:
                prompt_callback(index, prompt)
            if wait_callback is not None:
                wait_callback()

            report = run_live_translation(
                config,
                duration_seconds=segment_timeout,
                max_segments=1,
                on_asr_result=on_asr_result,
                runtime=runtime,
            )
            asr_finals = [item for item in report.asr_report.results if item.is_final and item.text]
            translations = [item for item in report.translations if item.status in {"translated", "skipped", "error"}]
            last_asr = asr_finals[-1] if asr_finals else None
            last_translation = translations[-1] if translations else None
            entries.append(
                GuidedTranslationEntry(
                    prompt=prompt,
                    report=report,
                    asr_text=last_asr.text if last_asr else "",
                    translation_status=last_translation.status if last_translation else "missing",
                    translation_text=last_translation.text if last_translation else "",
                    detected_language=last_asr.language if last_asr else None,
                )
            )
    finally:
        runtime.asr.asr_service.close()
        runtime.asr.asr_service.join(timeout=30.0)
        runtime.translation_service.close()
        runtime.translation_service.join(timeout=config.translation.timeout_seconds)

    return GuidedTranslationReport(script_name=script_name, entries=entries, checks=checks)


def render_guided_translation_validation(report: GuidedTranslationReport) -> str:
    lines = [f"Validación guiada de traducción: {report.script_name}"]
    for index, entry in enumerate(report.entries, start=1):
        lines.append(f"{index}. Prompt: {entry.prompt}")
        lines.append(f"   ASR final: {entry.asr_text or '[vacío]'}")
        lines.append(f"   Estado traducción: {entry.translation_status}")
        lines.append(f"   Traducción: {entry.translation_text or '[vacío]'}")
        lines.append(f"   Idioma detectado: {entry.detected_language or '?'}")
    return "\n".join(lines)


def run_translation_benchmark(config: AppConfig) -> BenchmarkReport:
    events = []
    checks = []
    results = []

    cases = build_translation_benchmark_cases(config.target_language.value)
    from traductor_tiempo_real.traduccion.ollama import OllamaTranslationBackend

    with measure_stage(
        "translation.benchmark_backend_init",
        collector=events,
        metadata={"model": config.translation.preferred_model},
    ):
        backend = OllamaTranslationBackend(config.translation)
        checks.append(
            CheckResult(
                name="translation.benchmark.backend",
                status=CheckStatus.OK,
                message="Backend de benchmark de traducción inicializado.",
                details={"model": config.translation.preferred_model},
            )
        )

    with measure_stage("translation.benchmark_warmup", collector=events):
        backend.warmup()
        checks.append(
            CheckResult(
                name="translation.benchmark.warmup",
                status=CheckStatus.OK,
                message="Warmup del benchmark de traducción completado.",
            )
        )

    for case in cases:
        with measure_stage(
            "translation.benchmark_generate",
            collector=events,
            metadata={"label": case["label"], "target_language": config.target_language.value},
        ):
            import time

            started = time.perf_counter()
            translated_text, metadata = backend.translate(
                case["text"],
                source_language=case["source_language"],
                target_language=config.target_language.value,
            )
            latency_ms = (time.perf_counter() - started) * 1000

        results.append(
            {
                "label": case["label"],
                "source_language": case["source_language"],
                "target_language": config.target_language.value,
                "source_text": case["text"],
                "translation": translated_text,
                "latency_ms": latency_ms,
                **metadata,
            }
        )

    if all(item.get("parse_mode") == "json" and item.get("translation") for item in results):
        checks.append(
            CheckResult(
                name="translation.benchmark.clean_output",
                status=CheckStatus.OK,
                message="Las respuestas del benchmark se extrajeron desde JSON limpio sin texto extra.",
            )
        )
    else:
        checks.append(
            CheckResult(
                name="translation.benchmark.clean_output",
                status=CheckStatus.WARNING,
                message="Alguna respuesta del benchmark no llegó en JSON limpio o vino vacía.",
            )
        )

    return BenchmarkReport(
        name="benchmark_translation_sprint_3",
        environment={"project_root": str(config.project_root)},
        configuration={
            "backend": config.translation.backend,
            "model": config.translation.preferred_model,
            "target_language": config.target_language.value,
        },
        events=events,
        checks=checks,
        notes=[json.dumps(item, ensure_ascii=False) for item in results],
    )


def render_translation_benchmark(report: BenchmarkReport) -> str:
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
