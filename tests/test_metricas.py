from __future__ import annotations

from pathlib import Path
import sys
import unittest


SRC_PATH = Path(__file__).resolve().parents[1] / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from traductor_tiempo_real.metricas.reporte import BenchmarkReport
from traductor_tiempo_real.metricas.estadisticas import latency_summary, percentile
from traductor_tiempo_real.metricas.tiempo import measure_stage


class MetricasTestCase(unittest.TestCase):
    def test_measure_stage_registra_evento(self) -> None:
        events = []
        with measure_stage("prueba.metricas", collector=events, metadata={"tipo": "smoke"}):
            pass

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].stage, "prueba.metricas")
        self.assertEqual(events[0].metadata["tipo"], "smoke")
        self.assertGreaterEqual(events[0].duration_ms, 0)

    def test_reporte_serializa_eventos_y_checks(self) -> None:
        events = []
        with measure_stage("prueba.reporte", collector=events):
            pass

        report = BenchmarkReport(
            name="reporte_test",
            environment={"python_version": "3.12"},
            configuration={"target_language": "en"},
            events=events,
            checks=[],
        )

        payload = report.to_dict()
        self.assertEqual(payload["name"], "reporte_test")
        self.assertEqual(payload["events"][0]["stage"], "prueba.reporte")

    def test_percentiles_de_latencia(self) -> None:
        values = [100.0, 200.0, 300.0, 400.0]

        self.assertEqual(percentile(values, 50), 250.0)
        summary = latency_summary(values)
        self.assertEqual(summary["count"], 4)
        self.assertEqual(summary["p50_ms"], 250.0)
        self.assertEqual(summary["p95_ms"], 385.0)


if __name__ == "__main__":
    unittest.main()
