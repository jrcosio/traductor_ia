from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

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

    return parser


def render_config(target_language: str, debug: bool) -> str:
    config = build_default_app_config(target_language=target_language, debug=debug)
    payload = asdict(config)
    return json.dumps(payload, indent=2, ensure_ascii=False, default=str)


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
        print("Escuchando...")
        report = run_live_transcription(
            config=config,
            duration_seconds=args.seconds,
            max_segments=args.max_segments,
            enable_partials=not args.no_partials,
            on_result=lambda result: print(format_asr_result_line(result), flush=True),
        )
        if args.json:
            print(report.to_json())
        else:
            print(render_live_transcription_summary(report))
        return 0 if report.is_successful() else 1

    if args.command == "validar-asr-real":
        config = build_default_app_config(target_language=args.target_language, debug=args.debug)
        report = run_guided_validation(
            config,
            script_name=args.script,
            segment_timeout=args.segment_timeout,
            on_result=lambda result: print(format_asr_result_line(result), flush=True),
            prompt_callback=lambda index, prompt: print(f"Frase {index}: {prompt}"),
            wait_callback=lambda: input("Pulsa Enter y habla ahora... "),
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

    parser.error(f"Comando no soportado: {args.command}")
    return 2
