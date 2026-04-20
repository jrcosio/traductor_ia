from __future__ import annotations

import platform
import shutil
import subprocess
import sys
import wave
from dataclasses import asdict
from pathlib import Path

from traductor_tiempo_real.configuracion.modelos import AppConfig
from traductor_tiempo_real.metricas.eventos import CheckResult, CheckStatus
from traductor_tiempo_real.metricas.reporte import BenchmarkReport
from traductor_tiempo_real.metricas.tiempo import measure_stage


def inspect_sample(sample_path: Path) -> tuple[CheckResult, dict[str, object]]:
    if not sample_path.exists():
        return (
            CheckResult(
                name="sample.exists",
                status=CheckStatus.ERROR,
                message=f"No existe la muestra WAV: {sample_path}",
            ),
            {},
        )

    with wave.open(str(sample_path), "rb") as wav_file:
        metadata = {
            "channels": wav_file.getnchannels(),
            "sample_width": wav_file.getsampwidth(),
            "sample_rate": wav_file.getframerate(),
            "frame_count": wav_file.getnframes(),
            "duration_ms": round((wav_file.getnframes() / wav_file.getframerate()) * 1000, 3),
        }

    return (
        CheckResult(
            name="sample.inspect",
            status=CheckStatus.OK,
            message="Muestra WAV valida para benchmark base.",
            details=metadata,
        ),
        metadata,
    )


def list_ollama_models() -> tuple[CheckResult, list[str]]:
    ollama_path = shutil.which("ollama")
    if not ollama_path:
        return (
            CheckResult(
                name="ollama.binary",
                status=CheckStatus.ERROR,
                message="No se encontro el ejecutable de Ollama.",
            ),
            [],
        )

    try:
        completed = subprocess.run(
            [ollama_path, "list"],
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return (
            CheckResult(
                name="ollama.list",
                status=CheckStatus.ERROR,
                message="No se pudo consultar Ollama.",
                details={"error": str(exc), "path": ollama_path},
            ),
            [],
        )

    models: list[str] = []
    for line in completed.stdout.splitlines()[1:]:
        stripped = line.strip()
        if not stripped:
            continue
        models.append(stripped.split()[0])

    return (
        CheckResult(
            name="ollama.list",
            status=CheckStatus.OK,
            message="Consulta de modelos de Ollama completada.",
            details={"path": ollama_path, "models": models},
        ),
        models,
    )


def probe_model(model_name: str) -> CheckResult:
    ollama_path = shutil.which("ollama")
    if not ollama_path:
        return CheckResult(
            name="ollama.show",
            status=CheckStatus.ERROR,
            message="No se puede probar el modelo porque Ollama no esta disponible.",
        )

    try:
        completed = subprocess.run(
            [ollama_path, "show", model_name],
            check=True,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return CheckResult(
            name="ollama.show",
            status=CheckStatus.ERROR,
            message=f"No se pudo inspeccionar el modelo {model_name}.",
            details={"error": str(exc), "model": model_name},
        )

    return CheckResult(
        name="ollama.show",
        status=CheckStatus.OK,
        message=f"Modelo {model_name} accesible en Ollama.",
        details={"model": model_name, "stdout_preview": completed.stdout[:200]},
    )


def build_environment_snapshot(config: AppConfig) -> dict[str, object]:
    return {
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "project_root": str(config.project_root),
    }


def run_base_benchmark(config: AppConfig, sample_path: Path | None = None) -> BenchmarkReport:
    events = []
    checks = []
    environment = build_environment_snapshot(config)
    benchmark_config = config.benchmark
    effective_sample = sample_path or benchmark_config.default_sample

    with measure_stage("config.resolve", collector=events):
        configuration_snapshot = asdict(config)

    with measure_stage("sample.inspect", collector=events, metadata={"path": str(effective_sample)}):
        sample_check, sample_metadata = inspect_sample(effective_sample)
        checks.append(sample_check)

    with measure_stage("environment.ollama_list", collector=events):
        ollama_check, installed_models = list_ollama_models()
        checks.append(ollama_check)

    preferred_model = config.translation.preferred_model
    model_available = preferred_model in installed_models
    checks.append(
        CheckResult(
            name="translation.preferred_model",
            status=CheckStatus.OK if model_available else CheckStatus.WARNING,
            message=(
                f"Modelo preferido disponible: {preferred_model}"
                if model_available
                else f"Modelo preferido no disponible: {preferred_model}"
            ),
            details={
                "preferred_model": preferred_model,
                "candidate_models": list(config.translation.candidate_models),
                "installed_models": installed_models,
            },
        )
    )

    probe_target = preferred_model if model_available else (installed_models[0] if installed_models else "")
    if benchmark_config.run_model_probe and probe_target:
        with measure_stage("environment.ollama_show", collector=events, metadata={"model": probe_target}):
            checks.append(probe_model(probe_target))
    elif benchmark_config.run_model_probe:
        checks.append(
            CheckResult(
                name="ollama.show",
                status=CheckStatus.WARNING,
                message="No hay modelo disponible para probar con ollama show.",
            )
        )

    report = BenchmarkReport(
        name="benchmark_base_sprint_0",
        environment=environment,
        configuration=configuration_snapshot,
        events=events,
        checks=checks,
        notes=[
            "Sprint 0 valida estructura, configuracion, entorno y benchmark offline base.",
            f"Muestra usada: {effective_sample}",
            f"Duracion muestra ms: {sample_metadata.get('duration_ms', 'n/d')}",
        ],
    )
    return report


def render_report(report: BenchmarkReport) -> str:
    lines = [
        f"Benchmark: {report.name}",
        f"Exito global: {'si' if report.is_successful() else 'no'}",
        f"Eventos medidos: {len(report.events)}",
        f"Checks ejecutados: {len(report.checks)}",
        "",
        "Checks:",
    ]
    for check in report.checks:
        lines.append(f"- [{check.status}] {check.name}: {check.message}")

    lines.append("")
    lines.append("Duraciones:")
    for event in report.events:
        lines.append(f"- {event.stage}: {event.duration_ms:.3f} ms ({event.status})")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    from traductor_tiempo_real.cli import main as cli_main

    args = ["benchmark-base"]
    if argv:
        args.extend(argv)
    return cli_main(args)
