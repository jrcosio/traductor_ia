from __future__ import annotations

from pathlib import Path
import sys
import unittest


SRC_PATH = Path(__file__).resolve().parents[1] / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from traductor_tiempo_real.configuracion.idiomas import LanguageCode, get_language_option, parse_target_language, target_language_choices


class IdiomasTestCase(unittest.TestCase):
    def test_catalogo_cerrado_de_idiomas(self) -> None:
        self.assertEqual(target_language_choices(), ("es", "en", "fr", "it"))

    def test_parsea_idioma_valido(self) -> None:
        self.assertEqual(parse_target_language("FR"), LanguageCode.FR)

    def test_falla_con_idioma_no_soportado(self) -> None:
        with self.assertRaises(ValueError):
            parse_target_language("pt")

    def test_recupera_metadatos_del_idioma(self) -> None:
        option = get_language_option("it")
        self.assertEqual(option.label, "Italiano")
        self.assertEqual(option.prompt_name, "italiano")


if __name__ == "__main__":
    unittest.main()
