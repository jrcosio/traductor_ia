from __future__ import annotations

import json
from urllib import request

from traductor_tiempo_real.configuracion.idiomas import SUPPORTED_TARGET_LANGUAGES
from traductor_tiempo_real.configuracion.modelos import TranslationConfig


LANGUAGE_NAME_BY_CODE = {
    option.code.value: option.prompt_name for option in SUPPORTED_TARGET_LANGUAGES.values()
}


def get_language_name(value: str | None) -> str:
    if not value:
        return "desconocido"
    return LANGUAGE_NAME_BY_CODE.get(value.lower(), value.lower())


def build_translation_system_prompt() -> str:
    return 'Traduce fielmente. Responde solo JSON válido: {"translation":"..."}.'


def build_translation_user_prompt(source_text: str, source_language: str | None, target_language: str) -> str:
    return (
        f"Origen: {get_language_name(source_language)}\n"
        f"Destino: {get_language_name(target_language)}\n"
        f"Texto: {source_text}"
    )


def extract_translation_from_content(content: str) -> tuple[str, str]:
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return text.strip().strip('"'), "raw"

    if isinstance(payload, dict) and isinstance(payload.get("translation"), str):
        return payload["translation"].strip(), "json"

    return text.strip().strip('"'), "raw"


class OllamaTranslationBackend:
    def __init__(self, config: TranslationConfig) -> None:
        self._config = config

    def warmup(self) -> None:
        payload = {
            "model": self._config.preferred_model,
            "messages": [
                {"role": "system", "content": build_translation_system_prompt()},
                {"role": "user", "content": build_translation_user_prompt("Hola.", "es", "en")},
            ],
            "stream": False,
            "keep_alive": self._config.keep_alive,
            "think": self._config.think,
            "options": {"temperature": 0.0, "num_predict": min(self._config.num_predict, 16)},
        }
        if self._config.structured_output:
            payload["format"] = _translation_response_format()
        self._post_chat(payload)

    def translate(self, source_text: str, *, source_language: str | None, target_language: str) -> tuple[str, dict[str, object]]:
        payload = {
            "model": self._config.preferred_model,
            "messages": [
                {"role": "system", "content": build_translation_system_prompt()},
                {
                    "role": "user",
                    "content": build_translation_user_prompt(
                        source_text=source_text,
                        source_language=source_language,
                        target_language=target_language,
                    ),
                },
            ],
            "stream": self._config.stream,
            "think": self._config.think,
            "keep_alive": self._config.keep_alive,
            "options": {"temperature": self._config.temperature, "num_predict": self._config.num_predict},
        }
        if self._config.structured_output:
            payload["format"] = _translation_response_format()

        response_payload = self._post_chat(payload)
        message = response_payload.get("message", {})
        translation, parse_mode = extract_translation_from_content(message.get("content", ""))
        metadata = {
            "parse_mode": parse_mode,
            "total_duration_ms": response_payload.get("total_duration", 0) / 1_000_000,
            "load_duration_ms": response_payload.get("load_duration", 0) / 1_000_000,
            "prompt_eval_count": response_payload.get("prompt_eval_count", 0),
            "eval_count": response_payload.get("eval_count", 0),
            "eval_duration_ms": response_payload.get("eval_duration", 0) / 1_000_000,
        }
        return translation, metadata

    def _post_chat(self, payload: dict[str, object]) -> dict[str, object]:
        data = json.dumps(payload).encode()
        req = request.Request(
            f"{self._config.base_url}/api/chat",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        with request.urlopen(req, timeout=self._config.timeout_seconds) as response:
            return json.loads(response.read().decode())


def _translation_response_format() -> dict[str, object]:
    return {
        "type": "object",
        "properties": {"translation": {"type": "string"}},
        "required": ["translation"],
    }
