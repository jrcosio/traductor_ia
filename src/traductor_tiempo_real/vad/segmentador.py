from __future__ import annotations

from collections import deque
from math import ceil
from time import monotonic
from uuid import uuid4

import numpy as np

from traductor_tiempo_real.audio.modelos import ActiveSpeechSnapshot, AudioFrame, SpeechSegment
from traductor_tiempo_real.configuracion.modelos import AudioConfig, VadConfig


class SpeechSegmenter:
    def __init__(self, audio_config: AudioConfig, vad_config: VadConfig) -> None:
        self._audio_config = audio_config
        self._vad_config = vad_config
        self._frame_ms = (audio_config.blocksize / audio_config.sample_rate) * 1000
        self._pre_roll_frames = max(1, ceil(vad_config.pre_roll_ms / self._frame_ms))
        self._hangover_frames = max(1, ceil(vad_config.hangover_ms / self._frame_ms))
        self._max_segment_frames = max(1, ceil(vad_config.max_segment_ms / self._frame_ms))
        self._pre_roll: deque[AudioFrame] = deque(maxlen=self._pre_roll_frames)
        self._active_frames: list[AudioFrame] = []
        self._active = False
        self._last_speech_at: float | None = None
        self._last_score: float | None = None
        self._silence_run = 0
        self._current_segment_id: str | None = None

    @property
    def is_active(self) -> bool:
        return self._active

    def process_frame(self, frame: AudioFrame, *, is_speech: bool, score: float | None = None) -> list[SpeechSegment]:
        if not self._active:
            self._pre_roll.append(frame)
            if is_speech:
                self._active = True
                self._current_segment_id = uuid4().hex
                self._active_frames = list(self._pre_roll)
                self._pre_roll.clear()
                self._last_speech_at = frame.created_at
                self._last_score = score
                self._silence_run = 0
            return []

        self._active_frames.append(frame)
        if is_speech:
            self._last_speech_at = frame.created_at
            self._last_score = score
            self._silence_run = 0
        else:
            self._silence_run += 1

        if len(self._active_frames) >= self._max_segment_frames:
            return [self._finalize(reason="max_segment", score=score)]

        if not is_speech and self._silence_run >= self._hangover_frames:
            return [self._finalize(reason="hangover", score=score)]

        return []

    def flush(self) -> list[SpeechSegment]:
        if not self._active_frames:
            return []
        return [self._finalize(reason="flush")]

    def snapshot(self) -> ActiveSpeechSnapshot | None:
        if not self._active_frames or self._current_segment_id is None:
            return None

        frames = list(self._active_frames)
        samples = np.concatenate([frame.audio for frame in frames]).astype(np.float32, copy=False)
        started_at = frames[0].created_at
        updated_at = frames[-1].created_at
        return ActiveSpeechSnapshot(
            segment_id=self._current_segment_id,
            created_at=monotonic(),
            started_at=started_at,
            updated_at=updated_at,
            duration_ms=(samples.size / self._audio_config.sample_rate) * 1000,
            sample_rate=self._audio_config.sample_rate,
            frame_count=len(frames),
            samples=samples,
            energy_rms=float(np.sqrt(np.mean(np.square(samples)))) if samples.size else 0.0,
            metadata={"last_score": self._last_score},
        )

    def _finalize(self, *, reason: str, score: float | None = None) -> SpeechSegment:
        frames = list(self._active_frames)
        samples = np.concatenate([frame.audio for frame in frames]).astype(np.float32, copy=False)
        started_at = frames[0].created_at
        finished_at = frames[-1].created_at
        created_at = monotonic()
        last_speech_at = self._last_speech_at or finished_at
        segment = SpeechSegment(
            segment_id=self._current_segment_id or uuid4().hex,
            created_at=created_at,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=(samples.size / self._audio_config.sample_rate) * 1000,
            closure_latency_ms=max(0.0, (created_at - last_speech_at) * 1000),
            sample_rate=self._audio_config.sample_rate,
            frame_count=len(frames),
            samples=samples,
            energy_rms=float(np.sqrt(np.mean(np.square(samples)))) if samples.size else 0.0,
            metadata={"reason": reason, "last_score": score},
        )
        self._active = False
        self._active_frames = []
        self._silence_run = 0
        self._last_speech_at = None
        self._last_score = None
        self._current_segment_id = None
        return segment
