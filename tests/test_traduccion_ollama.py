from __future__ import annotations

from pathlib import Path
import sys
import unittest


SRC_PATH = Path(__file__).resolve().parents[1] / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from traductor_tiempo_real.traduccion.ollama import (
    build_translation_system_prompt,
    build_translation_user_prompt,
    extract_translation_from_content,
)


class TraduccionOllamaTestCase(unittest.TestCase):
    def test_prompt_sistema_es_minimo_y_exige_json(self) -> None:
        prompt = build_translation_system_prompt()
        self.assertIn("JSON", prompt)
        self.assertIn("translation", prompt)
        self.assertIn("No añadas explicaciones", prompt)

    def test_prompt_usuario_incluye_idiomas_y_texto(self) -> None:
        prompt = build_translation_user_prompt(
            source_text="Hola, esto es una prueba.",
            source_language="es",
            target_language="en",
        )
        self.assertIn("español", prompt)
        self.assertIn("inglés", prompt)
        self.assertIn("Hola, esto es una prueba.", prompt)

    def test_parsea_json_con_bloque_markdown(self) -> None:
        content = "```json\n{\n  \"translation\": \"Hello, this is a test.\"\n}\n```"
        translation, parse_mode = extract_translation_from_content(content)
        self.assertEqual(translation, "Hello, this is a test.")
        self.assertEqual(parse_mode, "json")

    def test_hace_fallback_a_texto_plano(self) -> None:
        translation, parse_mode = extract_translation_from_content("Hello, this is a test.")
        self.assertEqual(translation, "Hello, this is a test.")
        self.assertEqual(parse_mode, "raw")


if __name__ == "__main__":
    unittest.main()
