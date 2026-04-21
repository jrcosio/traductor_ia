from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from traductor_tiempo_real.asr.servicio import AsrProcessingService
from traductor_tiempo_real.audio.captura import validate_default_input_settings
from traductor_tiempo_real.configuracion.modelos import AppConfig
from traductor_tiempo_real.metricas.eventos import CheckResult, CheckStatus, MetricEvent
from traductor_tiempo_real.metricas.tiempo import measure_stage
from traductor_tiempo_real.traduccion.servicio import TranslationProcessingService
from traductor_tiempo_real.tts.kokoro import get_voice_for_language
from traductor_tiempo_real.tts.reproductor import SoundDeviceAudioPlayer
from traductor_tiempo_real.tts.servicio import TtsProcessingService
from traductor_tiempo_real.vad.silero import SileroSpeechDetector


StartupCallback = Callable[[int, int, str], None]


@dataclass(slots=True)
class AsrRuntime:
    device_info: dict[str, object]
    detector: SileroSpeechDetector
    asr_service: AsrProcessingService
    events: list[MetricEvent]
    checks: list[CheckResult]


@dataclass(slots=True)
class TranslationRuntime:
    asr: AsrRuntime
    translation_service: TranslationProcessingService
    events: list[MetricEvent]
    checks: list[CheckResult]


@dataclass(slots=True)
class TtsRuntime:
    output_device_info: dict[str, object] | None
    tts_service: TtsProcessingService
    events: list[MetricEvent]
    checks: list[CheckResult]


@dataclass(slots=True)
class SpeechRuntime:
    translation: TranslationRuntime
    tts: TtsRuntime


def _emit_step(callback: StartupCallback | None, index: int, total: int, message: str) -> None:
    if callback is not None:
        callback(index, total, message)


def bootstrap_asr_runtime(config: AppConfig, *, on_step: StartupCallback | None = None) -> AsrRuntime:
    total_steps = 4
    events: list[MetricEvent] = []
    checks: list[CheckResult] = []

    with measure_stage("startup.audio_input", collector=events):
        device_info = validate_default_input_settings(config.audio)
        checks.append(
            CheckResult(
                name="startup.audio_input",
                status=CheckStatus.OK,
                message="Entrada de audio validada.",
                details={"name": device_info["name"], "sample_rate": config.audio.sample_rate},
            )
        )
    _emit_step(on_step, 1, total_steps, f"Micrófono listo: {device_info['name']}")

    with measure_stage("startup.vad_load", collector=events):
        detector = SileroSpeechDetector(config.vad)
        checks.append(
            CheckResult(
                name="startup.vad",
                status=CheckStatus.OK,
                message="Silero VAD cargado.",
            )
        )
    _emit_step(on_step, 2, total_steps, "VAD cargado")

    service = AsrProcessingService(config.asr, collector=events, checks=checks)
    service.initialize_backend()
    _emit_step(on_step, 3, total_steps, "Whisper cargado")

    service.warmup()
    _emit_step(on_step, 4, total_steps, "Whisper listo")

    service.start()
    return AsrRuntime(
        device_info=device_info,
        detector=detector,
        asr_service=service,
        events=events,
        checks=checks,
    )


def bootstrap_translation_runtime(
    config: AppConfig,
    *,
    on_step: StartupCallback | None = None,
    result_callback=None,
) -> TranslationRuntime:
    total_steps = 6

    def asr_step(index: int, _total: int, message: str) -> None:
        _emit_step(on_step, index, total_steps, message)

    asr_runtime = bootstrap_asr_runtime(config, on_step=asr_step)

    translation_events: list[MetricEvent] = []
    translation_checks: list[CheckResult] = []
    translation_service = TranslationProcessingService(
        config.translation,
        collector=translation_events,
        checks=translation_checks,
        result_callback=result_callback,
    )
    translation_service.initialize_backend()
    _emit_step(on_step, 5, total_steps, f"Ollama listo: {config.translation.preferred_model}")

    translation_service.warmup()
    _emit_step(on_step, 6, total_steps, "Traducción caliente")

    translation_service.start()
    return TranslationRuntime(
        asr=asr_runtime,
        translation_service=translation_service,
        events=translation_events,
        checks=translation_checks,
    )


def bootstrap_tts_runtime(
    config: AppConfig,
    *,
    on_step: StartupCallback | None = None,
    result_callback=None,
    play_audio: bool = True,
) -> TtsRuntime:
    total_steps = 4
    events: list[MetricEvent] = []
    checks: list[CheckResult] = []
    player = SoundDeviceAudioPlayer(config.tts)

    output_device_info = None
    if play_audio:
        with measure_stage("startup.audio_output", collector=events):
            output_device_info = player.validate_output_settings(sample_rate=config.tts.sample_rate)
            checks.append(
                CheckResult(
                    name="startup.audio_output",
                    status=CheckStatus.OK,
                    message="Salida de audio validada.",
                    details={"name": output_device_info["name"], "sample_rate": config.tts.sample_rate},
                )
            )
        _emit_step(on_step, 1, total_steps, f"Salida lista: {output_device_info['name']}")

        with measure_stage("startup.audio_output_warmup", collector=events):
            player.warmup_output(sample_rate=config.tts.sample_rate)
            checks.append(
                CheckResult(
                    name="startup.audio_output_warmup",
                    status=CheckStatus.OK,
                    message="Salida de audio precalentada.",
                )
            )
        _emit_step(on_step, 2, total_steps, "Salida de audio preparada")
    else:
        _emit_step(on_step, 1, total_steps, "Salida de audio omitida por modo mute")
        _emit_step(on_step, 2, total_steps, "Preparación de salida omitida por modo mute")

    tts_service = TtsProcessingService(
        config.tts,
        target_language=config.target_language.value,
        collector=events,
        checks=checks,
        player=player,
        result_callback=result_callback,
        play_audio=play_audio,
    )
    tts_service.initialize_backend()
    _emit_step(on_step, 3, total_steps, "Kokoro cargado")

    tts_service.warmup()
    voice = get_voice_for_language(config.target_language.value, config.tts)
    if voice is None:
        _emit_step(on_step, 4, total_steps, f"TTS sin voz para {config.target_language.value} (pendiente)")
        checks.append(
            CheckResult(
                name="startup.tts_voice",
                status=CheckStatus.WARNING,
                message="No hay voz TTS configurada para el idioma destino.",
                details={"language": config.target_language.value},
            )
        )
    else:
        _emit_step(on_step, 4, total_steps, f"TTS listo: {voice}")

    tts_service.start()
    return TtsRuntime(
        output_device_info=output_device_info,
        tts_service=tts_service,
        events=events,
        checks=checks,
    )


def bootstrap_speech_runtime(
    config: AppConfig,
    *,
    on_step: StartupCallback | None = None,
    translation_result_callback=None,
    tts_result_callback=None,
    play_audio: bool = True,
) -> SpeechRuntime:
    total_steps = 10

    def translation_step(index: int, _total: int, message: str) -> None:
        _emit_step(on_step, index, total_steps, message)

    translation_runtime = bootstrap_translation_runtime(
        config,
        on_step=translation_step,
        result_callback=translation_result_callback,
    )

    def tts_step(index: int, _total: int, message: str) -> None:
        _emit_step(on_step, index + 6, total_steps, message)

    tts_runtime = bootstrap_tts_runtime(
        config,
        on_step=tts_step,
        result_callback=tts_result_callback,
        play_audio=play_audio,
    )

    return SpeechRuntime(translation=translation_runtime, tts=tts_runtime)
