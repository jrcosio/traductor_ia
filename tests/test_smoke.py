from __future__ import annotations

from pathlib import Path
import sys
import unittest
from dataclasses import replace


SRC_PATH = Path(__file__).resolve().parents[1] / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from traductor_tiempo_real.benchmark_base import run_base_benchmark
from traductor_tiempo_real.configuracion.carga import build_default_app_config
from traductor_tiempo_real.configuracion.modelos import BenchmarkConfig


class SmokeTestCase(unittest.TestCase):
    def test_import_y_configuracion_basica(self) -> None:
        config = build_default_app_config(target_language="es")
        self.assertEqual(config.target_language.value, "es")

    def test_benchmark_base_ejecutable(self) -> None:
        config = build_default_app_config()
        config = replace(
            config,
            benchmark=BenchmarkConfig(
                default_sample=config.benchmark.default_sample,
                run_model_probe=False,
            ),
        )
        report = run_base_benchmark(config)
        self.assertTrue(report.events)
        self.assertTrue(report.checks)
        self.assertEqual(report.name, "benchmark_base_sprint_0")


if __name__ == "__main__":
    unittest.main()
