from __future__ import annotations

import queue
import threading
from itertools import count
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .audio import SAMPLE_RATE
from .text import clean_transcript, merge_transcripts, split_audio


@dataclass(slots=True)
class TranscriptionJob:
    audio: np.ndarray
    final: bool
    callback: Callable[[str, bool], None]
    error_callback: Callable[[str], None]


class TranscriptionEngine:
    def __init__(
        self,
        model_name: str,
        model_dir: Path,
        quantization: str | None = "int8",
    ):
        self.model_name = model_name
        self.model_dir = model_dir
        self.quantization = quantization
        self._model = None
        self._model_lock = threading.Lock()
        self._queue: queue.PriorityQueue[
            tuple[int, int, TranscriptionJob | None]
        ] = queue.PriorityQueue()
        self._sequence = count()
        self._cancel_partials_before = -1
        self._partial_pending = False
        self._lock = threading.Lock()
        self._thread = threading.Thread(
            target=self._run,
            name="GigaFlow-ASR",
            daemon=True,
        )
        self._thread.start()

    def preload(self) -> None:
        threading.Thread(
            target=self._preload_safely,
            name="GigaFlow-ASR-Preload",
            daemon=True,
        ).start()

    def _preload_safely(self) -> None:
        try:
            self._load_model()
        except Exception:
            # A normal transcription will report a useful error in the UI.
            return

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
        job = TranscriptionJob(
                audio=audio.copy(),
                final=final,
                callback=callback,
                error_callback=error_callback,
            )
        self._queue.put(
            (
                0 if final else 10,
                sequence,
                job,
            )
        )
        return True

    def _load_model(self):
        if self._model is not None:
            return self._model
        import onnx_asr

        with self._model_lock:
            if self._model is not None:
                return self._model
            # onnx-asr downloads a supported model only when its final
            # directory does not exist yet.
            self.model_dir.parent.mkdir(parents=True, exist_ok=True)
            kwargs = {}
            if self.quantization:
                kwargs["quantization"] = self.quantization
            self._model = onnx_asr.load_model(
                self.model_name,
                str(self.model_dir),
                **kwargs,
            )
            (self.model_dir / ".ready").write_text(
                "GigaFlow model ready\n",
                encoding="utf-8",
            )
        return self._model

    def _recognize(self, audio: np.ndarray, final: bool) -> str:
        model = self._load_model()
        if final:
            chunks = split_audio(audio)
        else:
            # The overlay shows only one short line, so reprocessing a full
            # 20-second window wastes CPU and can delay the final result.
            chunks = [audio[-6 * SAMPLE_RATE :]]
        parts = [
            clean_transcript(model.recognize(chunk, sample_rate=SAMPLE_RATE))
            for chunk in chunks
        ]
        return merge_transcripts(parts)

    def _run(self) -> None:
        while True:
            _, sequence, job = self._queue.get()
            if job is None:
                return
            if not job.final and sequence < self._cancel_partials_before:
                with self._lock:
                    self._partial_pending = False
                self._queue.task_done()
                continue
            try:
                text = self._recognize(job.audio, job.final)
                job.callback(text, job.final)
            except Exception as exc:
                job.error_callback(f"{type(exc).__name__}: {exc}")
            finally:
                if not job.final:
                    with self._lock:
                        self._partial_pending = False
                self._queue.task_done()

    def close(self) -> None:
        self._queue.put((99, next(self._sequence), None))
