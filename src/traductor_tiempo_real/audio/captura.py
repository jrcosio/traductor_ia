from __future__ import annotations

from collections import deque
from threading import Condition
from time import monotonic
from uuid import uuid4

import numpy as np

from traductor_tiempo_real.audio.modelos import AudioFrame
from traductor_tiempo_real.configuracion.modelos import AudioConfig


def get_sounddevice_module():
    import sounddevice as sounddevice

    return sounddevice


def normalize_audio_chunk(indata: np.ndarray) -> np.ndarray:
    chunk = np.asarray(indata, dtype=np.float32)
    if chunk.ndim == 1:
        mono = chunk
    elif chunk.ndim == 2:
        if chunk.shape[1] == 1:
            mono = chunk[:, 0]
        else:
            mono = chunk.mean(axis=1)
    else:
        raise ValueError(f"Forma de audio no soportada: {chunk.shape}")
    return np.array(mono, dtype=np.float32, copy=True)


class AudioRingBuffer:
    def __init__(self, max_frames: int) -> None:
        if max_frames <= 0:
            raise ValueError("max_frames debe ser mayor que cero")
        self._max_frames = max_frames
        self._frames: deque[AudioFrame] = deque()
        self._dropped_chunks = 0
        self._condition = Condition()

    @property
    def dropped_chunks(self) -> int:
        return self._dropped_chunks

    @property
    def size(self) -> int:
        with self._condition:
            return len(self._frames)

    def push(self, frame: AudioFrame) -> None:
        with self._condition:
            if len(self._frames) >= self._max_frames:
                self._frames.popleft()
                self._dropped_chunks += 1
            self._frames.append(frame)
            self._condition.notify()

    def pop(self, timeout: float | None = None) -> AudioFrame | None:
        with self._condition:
            if not self._frames:
                self._condition.wait(timeout=timeout)
            if not self._frames:
                return None
            return self._frames.popleft()

    def drain(self) -> list[AudioFrame]:
        with self._condition:
            frames = list(self._frames)
            self._frames.clear()
            return frames


def probe_default_input_device(sounddevice_module=None) -> dict[str, object]:
    sounddevice = sounddevice_module or get_sounddevice_module()
    info = sounddevice.query_devices(None, "input")
    if info["max_input_channels"] < 1:
        raise RuntimeError("El dispositivo de entrada por defecto no admite captura de audio")
    return dict(info)


def validate_default_input_settings(config: AudioConfig, sounddevice_module=None) -> dict[str, object]:
    sounddevice = sounddevice_module or get_sounddevice_module()
    info = probe_default_input_device(sounddevice)
    sounddevice.check_input_settings(
        device=config.device,
        channels=config.capture_channels,
        dtype=config.dtype,
        samplerate=config.sample_rate,
    )
    return info


class MicrophoneCapture:
    def __init__(self, config: AudioConfig, *, sounddevice_module=None) -> None:
        self._config = config
        self._sounddevice = sounddevice_module or get_sounddevice_module()
        self._buffer = AudioRingBuffer(config.queue_max_frames)
        self._stream = None
        self._device_info: dict[str, object] | None = None
        self._status_messages: list[str] = []

    @property
    def device_info(self) -> dict[str, object] | None:
        return self._device_info

    @property
    def dropped_chunks(self) -> int:
        return self._buffer.dropped_chunks

    @property
    def pending_chunks(self) -> int:
        return self._buffer.size

    @property
    def status_messages(self) -> tuple[str, ...]:
        return tuple(self._status_messages)

    def _callback(self, indata, frames: int, time_info, status) -> None:
        overflowed = bool(status)
        if overflowed:
            self._status_messages.append(str(status))

        frame = AudioFrame(
            frame_id=uuid4().hex,
            created_at=monotonic(),
            sample_rate=self._config.sample_rate,
            channels=self._config.channels,
            frame_count=frames,
            audio=normalize_audio_chunk(indata),
            overflowed=overflowed,
        )
        self._buffer.push(frame)

    def start(self) -> "MicrophoneCapture":
        self._device_info = validate_default_input_settings(self._config, self._sounddevice)
        self._stream = self._sounddevice.InputStream(
            device=self._config.device,
            channels=self._config.capture_channels,
            dtype=self._config.dtype,
            samplerate=self._config.sample_rate,
            blocksize=self._config.blocksize,
            callback=self._callback,
        )
        self._stream.start()
        return self

    def stop(self) -> None:
        if self._stream is None:
            return
        self._stream.stop()
        self._stream.close()
        self._stream = None

    def read_frame(self, timeout: float | None = None) -> AudioFrame | None:
        return self._buffer.pop(timeout=timeout)

    def __enter__(self) -> "MicrophoneCapture":
        return self.start()

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()
