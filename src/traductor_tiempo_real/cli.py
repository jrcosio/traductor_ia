from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

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

    parser.error(f"Comando no soportado: {args.command}")
    return 2
