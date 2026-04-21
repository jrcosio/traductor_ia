from __future__ import annotations

from collections.abc import Iterable

import numpy as np

from traductor_tiempo_real.configuracion.modelos import TtsConfig


def get_sounddevice_module():
    import sounddevice as sounddevice

    return sounddevice


def probe_default_output_device(sounddevice_module=None) -> dict[str, object]:
    sounddevice = sounddevice_module or get_sounddevice_module()
    info = sounddevice.query_devices(None, "output")
    if info["max_output_channels"] < 1:
        raise RuntimeError("El dispositivo de salida por defecto no admite reproducción de audio")
    return dict(info)


class SoundDeviceAudioPlayer:
    def __init__(self, config: TtsConfig, *, sounddevice_module=None) -> None:
        self._config = config
        self._sounddevice = sounddevice_module or get_sounddevice_module()

    def validate_output_settings(self, *, sample_rate: int | None = None) -> dict[str, object]:
        info = probe_default_output_device(self._sounddevice)
        self._sounddevice.check_output_settings(
            device=self._config.device,
            channels=self._config.channels,
            dtype=self._config.dtype,
            samplerate=sample_rate or self._config.sample_rate,
        )
        return info

    def warmup_output(self, *, sample_rate: int | None = None) -> None:
        samplerate = sample_rate or self._config.sample_rate
        stream = self._sounddevice.OutputStream(
            device=self._config.device,
            samplerate=samplerate,
            channels=self._config.channels,
            dtype=self._config.dtype,
            blocksize=self._config.blocksize,
        )
        try:
            stream.start()
            silence = np.zeros((self._config.blocksize, self._config.channels), dtype=np.float32)
            stream.write(silence)
            stream.stop()
        finally:
            stream.close()

    def play_chunks(self, chunks: Iterable[np.ndarray], *, sample_rate: int, play_audio: bool = True) -> dict[str, float]:
        total_samples = 0
        first_chunk_ready = False
        if play_audio:
            stream = self._sounddevice.OutputStream(
                device=self._config.device,
                samplerate=sample_rate,
                channels=self._config.channels,
                dtype=self._config.dtype,
                blocksize=self._config.blocksize,
            )
            stream.start()
        else:
            stream = None

        try:
            for chunk in chunks:
                if chunk.size == 0:
                    continue
                audio = np.asarray(chunk, dtype=np.float32).reshape(-1, 1)
                total_samples += audio.shape[0]
                if play_audio and stream is not None:
                    stream.write(audio)
                if not first_chunk_ready:
                    first_chunk_ready = True
            if play_audio and stream is not None:
                stream.stop()
        finally:
            if stream is not None:
                stream.close()

        return {
            "audio_duration_ms": (total_samples / sample_rate) * 1000 if total_samples else 0.0,
            "sample_count": float(total_samples),
            "first_chunk_ready": 1.0 if first_chunk_ready else 0.0,
        }
