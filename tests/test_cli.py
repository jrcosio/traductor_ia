from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch


SRC_PATH = Path(__file__).resolve().parents[1] / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from traductor_tiempo_real.cli import build_parser, prompt_for_target_language, resolve_target_language


class CliTestCase(unittest.TestCase):
    def test_selector_acepta_numero_de_idioma(self) -> None:
        outputs = []

        selected = prompt_for_target_language(
            input_callback=lambda _prompt: "3",
            output_callback=outputs.append,
        )

        self.assertEqual(selected, "fr")
        self.assertIn("Selecciona idioma destino:", outputs)

    def test_resuelve_target_language_explicito(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--target-language", "it", "traducir-en-vivo", "--seconds", "1"])

        self.assertEqual(resolve_target_language(args, parser), "it")

    def test_resuelve_target_language_interactivo_con_selector(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["traducir-en-vivo", "--seconds", "1"])

        with patch("traductor_tiempo_real.cli.prompt_for_target_language", return_value="es"):
            self.assertEqual(resolve_target_language(args, parser), "es")

    def test_json_interactivo_exige_target_language(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["traducir-en-vivo", "--json"])

        with self.assertRaises(SystemExit):
            resolve_target_language(args, parser)

    def test_comando_no_interactivo_conserva_ingles_por_defecto(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["benchmark-traduccion"])

        self.assertEqual(resolve_target_language(args, parser), "en")


if __name__ == "__main__":
    unittest.main()
