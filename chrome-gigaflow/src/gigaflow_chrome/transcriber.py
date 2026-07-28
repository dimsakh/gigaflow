from __future__ import annotations

import queue
import threading
from collections.abc import Callable
from dataclasses import dataclass
from itertools import count
from pathlib import Path

import numpy as np

from .audio import SAMPLE_RATE
from .text import clean_transcript, merge_transcripts, split_audio


@dataclass(slots=True)
class Job:
    audio: np.ndarray
    final: bool
    callback: Callable[[str, bool], None]
    error_callback: Callable[[str], None]


class TranscriptionEngine:
    def __init__(self, model_dir: Path):
        self.model_dir = model_dir
        self._model = None
        self._model_lock = threading.Lock()
        self._queue: queue.PriorityQueue[tuple[int, int, Job | None]] = queue.PriorityQueue()
        self._sequence = count()
        self._partial_pending = False
        self._cancel_partials_before = -1
        self._lock = threading.Lock()
        threading.Thread(target=self._run, name="Chrome-GigaAM", daemon=True).start()

    def preload(self) -> None:
        threading.Thread(target=self._preload_safely, daemon=True).start()

    def _preload_safely(self) -> None:
        try:
            self._load_model()
        except Exception:
            return

    def _load_model(self):
        if self._model is not None:
            return self._model
        import onnx_asr

        with self._model_lock:
            if self._model is None:
                self.model_dir.parent.mkdir(parents=True, exist_ok=True)
                self._model = onnx_asr.load_model(
                    "gigaam-v3-e2e-rnnt",
                    str(self.model_dir),
                    quantization="int8",
                )
        return self._model

    def submit(
        self,
        audio: np.ndarray,
        *,
        final: bool,
        callback: Callable[[str, bool], None],
        error_callback: Callable[[str], None],
    ) -> bool:
        if audio.size < SAMPLE_RATE // 2:
            return False
        sequence = next(self._sequence)
        with self._lock:
            if not final and self._partial_pending:
                return False
            if not final:
                self._partial_pending = True
            else:
                self._cancel_partials_before = sequence
        self._queue.put(
            (
                0 if final else 10,
                sequence,
                Job(audio.copy(), final, callback, error_callback),
            )
        )
        return True

    def _recognize(self, audio: np.ndarray, final: bool) -> str:
        model = self._load_model()
        chunks = split_audio(audio) if final else [audio[-6 * SAMPLE_RATE :]]
        return merge_transcripts(
            [
                clean_transcript(model.recognize(chunk, sample_rate=SAMPLE_RATE))
                for chunk in chunks
            ]
        )

    def _run(self) -> None:
        while True:
            _, sequence, job = self._queue.get()
            if job is None:
                return
            try:
                if not job.final and sequence < self._cancel_partials_before:
                    continue
                job.callback(self._recognize(job.audio, job.final), job.final)
            except Exception as exc:
                job.error_callback(f"{type(exc).__name__}: {exc}")
            finally:
                if not job.final:
                    with self._lock:
                        self._partial_pending = False
                self._queue.task_done()

    def close(self) -> None:
        self._queue.put((99, next(self._sequence), None))
