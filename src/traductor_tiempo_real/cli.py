from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Callable

from traductor_tiempo_real.asr.diagnostico import (
    VALIDATION_SCRIPTS,
    format_asr_result_line,
    render_asr_benchmark,
    render_guided_validation,
    render_live_transcription_summary,
    run_asr_benchmark,
    run_guided_validation,
    run_live_transcription,
)
from traductor_tiempo_real.audio.diagnostico import render_capture_diagnostic, run_capture_diagnostic
from traductor_tiempo_real.benchmark_base import render_report, run_base_benchmark
from traductor_tiempo_real.configuracion.carga import build_default_app_config
from traductor_tiempo_real.configuracion.idiomas import target_language_choices
from traductor_tiempo_real.pipeline.orquestador import render_pipeline_summary, run_live_pipeline, run_pre_recorded_pipeline
from traductor_tiempo_real.traduccion.diagnostico import (
    format_translation_result_line,
    render_translation_benchmark,
    run_translation_benchmark,
)
from traductor_tiempo_real.tts.diagnostico import (
    format_tts_result_line,
    render_guided_speech_validation,
    render_live_speech_summary,
    render_tts_benchmark,
    render_tts_diagnostic,
    run_guided_speech_validation,
    run_live_speech,
    run_tts_benchmark,
    run_tts_diagnostic,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="traductor-ia",
        description="Herramientas base del proyecto de traduccion en tiempo real.",
    )
    parser.add_argument(
        "--target-language",
        choices=target_language_choices(),
        default="en",
        help="Idioma destino del MVP.",
    )
    parser.add_argument("--debug", action="store_true", help="Activa salida adicional.")

    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("info", help="Muestra la configuracion efectiva.")

    benchmark_parser = subparsers.add_parser(
        "benchmark-base",
        help="Ejecuta el benchmark offline base del Sprint 0.",
    )
    benchmark_parser.add_argument(
        "--sample",
        type=Path,
        default=None,
        help="Ruta al WAV de prueba.",
    )
    benchmark_parser.add_argument(
        "--json",
        action="store_true",
        help="Emite el reporte completo en JSON.",
    )

    capture_parser = subparsers.add_parser(
        "captura-diagnostico",
        help="Diagnostica captura y segmentacion con el micrófono por defecto.",
    )
    capture_parser.add_argument(
        "--seconds",
        type=float,
        default=10.0,
        help="Duración de la captura en segundos.",
    )
    capture_parser.add_argument(
        "--max-segments",
        type=int,
        default=None,
        help="Detiene la captura al alcanzar este número de segmentos.",
    )
    capture_parser.add_argument(
        "--json",
        action="store_true",
        help="Emite el reporte completo en JSON.",
    )

    live_parser = subparsers.add_parser(
        "transcribe-en-vivo",
        help="Captura desde micrófono y muestra transcripción en terminal.",
    )
    live_parser.add_argument(
        "--seconds",
        type=float,
        default=30.0,
        help="Duración máxima de la sesión en segundos.",
    )
    live_parser.add_argument(
        "--max-segments",
        type=int,
        default=None,
        help="Detiene la sesión al alcanzar este número de segmentos finales.",
    )
    live_parser.add_argument(
        "--no-partials",
        action="store_true",
        help="Desactiva resultados parciales.",
    )
    live_parser.add_argument(
        "--json",
        action="store_true",
        help="Emite el reporte final en JSON.",
    )

    validation_parser = subparsers.add_parser(
        "validar-asr-real",
        help="Ejecuta una validación guiada leyendo frases desde terminal.",
    )
    validation_parser.add_argument(
        "--script",
        choices=tuple(VALIDATION_SCRIPTS.keys()),
        default="es-basico",
        help="Script de frases a validar.",
    )
    validation_parser.add_argument(
        "--segment-timeout",
        type=float,
        default=8.0,
        help="Tiempo máximo por frase en segundos.",
    )
    validation_parser.add_argument(
        "--json",
        action="store_true",
        help="Emite el reporte final en JSON.",
    )

    asr_benchmark_parser = subparsers.add_parser(
        "benchmark-asr",
        help="Ejecuta benchmark real del ASR sobre WAVs locales.",
    )
    asr_benchmark_parser.add_argument(
        "--sample",
        type=Path,
        action="append",
        default=None,
        help="Ruta a un WAV. Puede repetirse varias veces.",
    )
    asr_benchmark_parser.add_argument(
        "--json",
        action="store_true",
        help="Emite el reporte completo en JSON.",
    )

    translation_live_parser = subparsers.add_parser(
        "traducir-en-vivo",
        help="Captura desde micrófono, transcribe y traduce en terminal.",
    )
    translation_live_parser.add_argument(
        "--seconds",
        type=float,
        default=30.0,
        help="Duración máxima de la sesión en segundos.",
    )
    translation_live_parser.add_argument(
        "--max-segments",
        type=int,
        default=None,
        help="Detiene la sesión al alcanzar este número de segmentos finales.",
    )
    translation_live_parser.add_argument(
        "--json",
        action="store_true",
        help="Emite el reporte final en JSON.",
    )
    translation_live_parser.add_argument(
        "--mute",
        action="store_true",
        help="Desactiva la reproducción de audio TTS durante la sesión.",
    )

    translation_validation_parser = subparsers.add_parser(
        "validar-traduccion-real",
        help="Ejecuta validación guiada de traducción leyendo frases desde terminal.",
    )
    translation_validation_parser.add_argument(
        "--script",
        choices=tuple(VALIDATION_SCRIPTS.keys()),
        default="es-basico",
        help="Script de frases a validar.",
    )
    translation_validation_parser.add_argument(
        "--segment-timeout",
        type=float,
        default=8.0,
        help="Tiempo máximo por frase en segundos.",
    )
    translation_validation_parser.add_argument(
        "--json",
        action="store_true",
        help="Emite el reporte final en JSON.",
    )
    translation_validation_parser.add_argument(
        "--mute",
        action="store_true",
        help="Desactiva la reproducción de audio TTS durante la validación.",
    )

    translation_benchmark_parser = subparsers.add_parser(
        "benchmark-traduccion",
        help="Ejecuta benchmark de traducción semántica sobre frases locales.",
    )
    translation_benchmark_parser.add_argument(
        "--json",
        action="store_true",
        help="Emite el reporte completo en JSON.",
    )

    tts_parser = subparsers.add_parser(
        "tts-diagnostico",
        help="Sintetiza y reproduce una frase con Kokoro en el idioma destino activo.",
    )
    tts_parser.add_argument(
        "--text",
        required=True,
        help="Texto a sintetizar.",
    )
    tts_parser.add_argument(
        "--mute",
        action="store_true",
        help="Sintetiza sin reproducir el audio.",
    )
    tts_parser.add_argument(
        "--json",
        action="store_true",
        help="Emite el reporte completo en JSON.",
    )

    tts_benchmark_parser = subparsers.add_parser(
        "benchmark-tts",
        help="Ejecuta benchmark de síntesis de voz del Sprint 4.",
    )
    tts_benchmark_parser.add_argument(
        "--play",
        action="store_true",
        help="Reproduce audio durante el benchmark para medir en condiciones reales.",
    )
    tts_benchmark_parser.add_argument(
        "--json",
        action="store_true",
        help="Emite el reporte completo en JSON.",
    )

    pipeline_live_parser = subparsers.add_parser(
        "pipeline-diagnostico",
        help="Ejecuta el pipeline completo con asyncio, colas acotadas y métricas end-to-end.",
    )
    pipeline_live_parser.add_argument(
        "--seconds",
        type=float,
        default=20.0,
        help="Duración máxima de la sesión en segundos.",
    )
    pipeline_live_parser.add_argument(
        "--max-segments",
        type=int,
        default=None,
        help="Detiene la sesión al alcanzar este número de segmentos finales.",
    )
    pipeline_live_parser.add_argument(
        "--mute",
        action="store_true",
        help="Desactiva la reproducción de audio TTS durante la sesión.",
    )
    pipeline_live_parser.add_argument(
        "--json",
        action="store_true",
        help="Emite el reporte completo en JSON.",
    )

    pipeline_benchmark_parser = subparsers.add_parser(
        "benchmark-pipeline",
        help="Ejecuta el pipeline completo sobre audio pregrabado.",
    )
    pipeline_benchmark_parser.add_argument(
        "--sample",
        type=Path,
        action="append",
        default=None,
        help="Ruta a un WAV. Puede repetirse varias veces.",
    )
    pipeline_benchmark_parser.add_argument(
        "--json",
        action="store_true",
        help="Emite el reporte completo en JSON.",
    )

    return parser


def render_config(target_language: str, debug: bool) -> str:
    config = build_default_app_config(target_language=target_language, debug=debug)
    payload = asdict(config)
    return json.dumps(payload, indent=2, ensure_ascii=False, default=str)


def build_startup_reporters(*, include_listening: bool) -> tuple[Callable[[int, int, str], None], Callable[[], None]]:
    state = {"started": False}

    def on_step(index: int, total: int, message: str) -> None:
        if not state["started"]:
            print("Inicializando sistema...", flush=True)
            state["started"] = True
        print(f"[{index}/{total}] {message}", flush=True)

    def on_ready() -> None:
        if not state["started"]:
            print("Inicializando sistema...", flush=True)
            state["started"] = True
        print("Sistema listo.", flush=True)
        if include_listening:
            print("Escuchando...", flush=True)

    return on_step, on_ready


def wait_for_user(prompt: str) -> None:
    try:
        input(prompt)
    except EOFError:
        return


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command in {None, "info"}:
        print(render_config(args.target_language, args.debug))
        return 0

    if args.command == "benchmark-base":
        config = build_default_app_config(target_language=args.target_language, debug=args.debug)
        report = run_base_benchmark(config=config, sample_path=args.sample)
        if args.json:
            print(report.to_json())
        else:
            print(render_report(report))
        return 0 if report.is_successful() else 1

    if args.command == "captura-diagnostico":
        config = build_default_app_config(target_language=args.target_language, debug=args.debug)
        report = run_capture_diagnostic(
            config=config,
            duration_seconds=args.seconds,
            max_segments=args.max_segments,
        )
        if args.json:
            print(report.to_json())
        else:
            print(render_capture_diagnostic(report))
        return 0 if report.is_successful() else 1

    if args.command == "transcribe-en-vivo":
        config = build_default_app_config(target_language=args.target_language, debug=args.debug)
        on_step, on_ready = build_startup_reporters(include_listening=True)
        report = run_live_transcription(
            config=config,
            duration_seconds=args.seconds,
            max_segments=args.max_segments,
            enable_partials=not args.no_partials,
            on_result=lambda result: print(format_asr_result_line(result), flush=True),
            on_startup_step=on_step,
            on_ready=on_ready,
        )
        if args.json:
            print(report.to_json())
        else:
            print(render_live_transcription_summary(report))
        return 0 if report.is_successful() else 1

    if args.command == "validar-asr-real":
        config = build_default_app_config(target_language=args.target_language, debug=args.debug)
        on_step, on_ready = build_startup_reporters(include_listening=False)
        report = run_guided_validation(
            config,
            script_name=args.script,
            segment_timeout=args.segment_timeout,
            on_result=lambda result: print(format_asr_result_line(result), flush=True),
            prompt_callback=lambda index, prompt: print(f"Frase {index}: {prompt}"),
            wait_callback=lambda: wait_for_user("Pulsa Enter y habla ahora... "),
            on_startup_step=on_step,
            on_ready=on_ready,
        )
        if args.json:
            print(report.to_json())
        else:
            print(render_guided_validation(report))
        return 0 if report.is_successful() else 1

    if args.command == "benchmark-asr":
        config = build_default_app_config(target_language=args.target_language, debug=args.debug)
        sample_paths = args.sample if args.sample else sorted((config.project_root / "samples" / "asr").glob("*.wav"))
        report = run_asr_benchmark(config, list(sample_paths))
        if args.json:
            print(report.to_json())
        else:
            print(render_asr_benchmark(report))
        return 0 if report.is_successful() else 1

    if args.command == "traducir-en-vivo":
        config = build_default_app_config(target_language=args.target_language, debug=args.debug)
        on_step, on_ready = build_startup_reporters(include_listening=True)
        report = run_live_speech(
            config,
            duration_seconds=args.seconds,
            max_segments=args.max_segments,
            play_audio=not args.mute,
            on_asr_result=lambda result: print(
                f"[ASR-FINAL][{result.language or '?'}][{result.latency_ms:.0f} ms] {result.text}",
                flush=True,
            ),
            on_translation_result=lambda result: print(format_translation_result_line(result), flush=True),
            on_tts_result=lambda result: print(format_tts_result_line(result), flush=True),
            on_startup_step=on_step,
            on_ready=on_ready,
        )
        if args.json:
            print(report.to_json())
        else:
            print(render_live_speech_summary(report))
        return 0 if report.is_successful() else 1

    if args.command == "validar-traduccion-real":
        config = build_default_app_config(target_language=args.target_language, debug=args.debug)
        on_step, on_ready = build_startup_reporters(include_listening=False)
        report = run_guided_speech_validation(
            config,
            script_name=args.script,
            segment_timeout=args.segment_timeout,
            play_audio=not args.mute,
            on_asr_result=lambda result: print(
                f"[ASR-FINAL][{result.language or '?'}][{result.latency_ms:.0f} ms] {result.text}",
                flush=True,
            ),
            on_translation_result=lambda result: print(format_translation_result_line(result), flush=True),
            on_tts_result=lambda result: print(format_tts_result_line(result), flush=True),
            prompt_callback=lambda index, prompt: print(f"Frase {index}: {prompt}"),
            wait_callback=lambda: wait_for_user("Pulsa Enter y habla ahora... "),
            on_startup_step=on_step,
            on_ready=on_ready,
        )
        if args.json:
            print(report.to_json())
        else:
            print(render_guided_speech_validation(report))
        return 0 if report.is_successful() else 1

    if args.command == "benchmark-traduccion":
        config = build_default_app_config(target_language=args.target_language, debug=args.debug)
        report = run_translation_benchmark(config)
        if args.json:
            print(report.to_json())
        else:
            print(render_translation_benchmark(report))
        return 0 if report.is_successful() else 1

    if args.command == "tts-diagnostico":
        config = build_default_app_config(target_language=args.target_language, debug=args.debug)
        on_step, on_ready = build_startup_reporters(include_listening=False)
        report = run_tts_diagnostic(
            config,
            text=args.text,
            play_audio=not args.mute,
            on_startup_step=on_step,
            on_ready=on_ready,
        )
        if args.json:
            print(report.to_json())
        else:
            print(render_tts_diagnostic(report))
        return 0 if report.is_successful() else 1

    if args.command == "benchmark-tts":
        config = build_default_app_config(target_language=args.target_language, debug=args.debug)
        report = run_tts_benchmark(config, play_audio=args.play)
        if args.json:
            print(report.to_json())
        else:
            print(render_tts_benchmark(report))
        return 0 if report.is_successful() else 1

    if args.command == "pipeline-diagnostico":
        config = build_default_app_config(target_language=args.target_language, debug=args.debug)
        on_step, on_ready = build_startup_reporters(include_listening=True)
        report = run_live_pipeline(
            config,
            duration_seconds=args.seconds,
            max_segments=args.max_segments,
            play_audio=not args.mute,
            on_startup_step=on_step,
            on_ready=on_ready,
            on_asr_result=lambda result: print(
                f"[ASR-FINAL][{result.language or '?'}][{result.latency_ms:.0f} ms] {result.text}",
                flush=True,
            ) if result.is_final else None,
            on_translation_result=lambda result: print(format_translation_result_line(result), flush=True),
            on_tts_result=lambda result: print(format_tts_result_line(result), flush=True),
        )
        if args.json:
            print(report.to_json())
        else:
            print(render_pipeline_summary(report))
        return 0 if report.is_successful() else 1

    if args.command == "benchmark-pipeline":
        config = build_default_app_config(target_language=args.target_language, debug=args.debug)
        sample_paths = args.sample if args.sample else sorted((config.project_root / "samples" / "asr").glob("*.wav"))
        report = run_pre_recorded_pipeline(config, sample_paths=list(sample_paths), play_audio=False)
        if args.json:
            print(report.to_json())
        else:
            print(render_pipeline_summary(report))
        return 0 if report.is_successful() else 1

    parser.error(f"Comando no soportado: {args.command}")
    return 2
