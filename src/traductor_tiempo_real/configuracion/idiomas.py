from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class LanguageCode(StrEnum):
    ES = "es"
    EN = "en"
    FR = "fr"
    DE = "de"
    IT = "it"


@dataclass(frozen=True, slots=True)
class LanguageOption:
    code: LanguageCode
    label: str
    prompt_name: str
    tts_name: str


SUPPORTED_TARGET_LANGUAGES: dict[LanguageCode, LanguageOption] = {
    LanguageCode.ES: LanguageOption(LanguageCode.ES, "Español", "español", "spanish"),
    LanguageCode.EN: LanguageOption(LanguageCode.EN, "Inglés", "inglés", "english"),
    LanguageCode.FR: LanguageOption(LanguageCode.FR, "Francés", "francés", "french"),
    LanguageCode.DE: LanguageOption(LanguageCode.DE, "Alemán", "alemán", "german"),
    LanguageCode.IT: LanguageOption(LanguageCode.IT, "Italiano", "italiano", "italian"),
}


def supported_target_languages() -> tuple[LanguageOption, ...]:
    return tuple(SUPPORTED_TARGET_LANGUAGES.values())


def target_language_choices() -> tuple[str, ...]:
    return tuple(option.code.value for option in supported_target_languages())


def parse_target_language(value: str | LanguageCode) -> LanguageCode:
    if isinstance(value, LanguageCode):
        return value

    normalized = value.strip().lower()
    try:
        return LanguageCode(normalized)
    except ValueError as exc:
        raise ValueError(
            f"Idioma destino no soportado: {value}. Opciones validas: {', '.join(target_language_choices())}"
        ) from exc


def get_language_option(value: str | LanguageCode) -> LanguageOption:
    code = parse_target_language(value)
    return SUPPORTED_TARGET_LANGUAGES[code]
