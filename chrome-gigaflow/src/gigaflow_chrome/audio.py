from __future__ import annotations

import threading
import time
from collections.abc import Callable

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16_000


class AudioRecorder:
    def __init__(self, on_level: Callable[[float], None]):
        self._on_level = on_level
        self._lock = threading.Lock()
        self._frames: list[np.ndarray] = []
        self._stream: sd.InputStream | None = None
        self._recording = False
        self._heard_voice = False
        self._last_voice_at = 0.0

    @property
    def recording(self) -> bool:
        return self._recording

    @property
    def heard_voice(self) -> bool:
        return self._heard_voice

    @property
    def silence_seconds(self) -> float:
        if not self._heard_voice:
            return 0.0
        return max(0.0, time.monotonic() - self._last_voice_at)

    def start(self) -> None:
        if self._recording:
            return
        with self._lock:
            self._frames.clear()
        self._heard_voice = False
        self._last_voice_at = 0.0
        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            blocksize=800,
            latency="low",
            callback=self._callback,
        )
        self._stream.start()
        self._recording = True

    def _callback(self, data: np.ndarray, frames: int, time_info, status) -> None:
        del frames, time_info, status
        mono = data[:, 0].copy()
        with self._lock:
            self._frames.append(mono)
        rms = float(np.sqrt(np.mean(np.square(mono), dtype=np.float64)))
        if rms >= 0.008:
            self._heard_voice = True
            self._last_voice_at = time.monotonic()
        self._on_level(min(1.0, max(0.0, rms * 12.0)))

    def snapshot(self) -> np.ndarray:
        with self._lock:
            if not self._frames:
                return np.empty(0, dtype=np.float32)
            return np.concatenate(self._frames).astype(np.float32, copy=False)

    def stop(self) -> np.ndarray:
        self._recording = False
        stream, self._stream = self._stream, None
        if stream is not None:
            stream.stop()
            stream.close()
        return self.snapshot()

    def cancel(self) -> None:
        self.stop()
        with self._lock:
            self._frames.clear()
