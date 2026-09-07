from __future__ import annotations

import logging
import sys
import threading
import time
from pathlib import Path

import numpy as np
from PySide6.QtCore import QObject, QTimer, Signal, Slot
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from .audio import AudioRecorder, SAMPLE_RATE
from .clipboard import (
    copy_text,
    foreground_external_window,
    paste_from_clipboard,
    send_backspaces,
    type_text,
)
from .config import AppConfig
from .hotkeys import GlobalHotkey
from .icons import application_icon, set_windows_app_id
from .paths import ensure_app_dirs
from .single_instance import SingleInstanceGuard
from .storage import HistoryStore
from .text import common_prefix_length, merge_transcripts, remove_filler_words
from .transcriber import TranscriptionEngine
from .ui.main_window import MainWindow
from .ui.model_setup import ModelSetupDialog
from .ui.overlay import ListeningOverlay
from .ui.theme import APP_STYLE


class EventBridge(QObject):
    hotkey = Signal()
    level = Signal(float)
    transcription = Signal(str, bool)
    chunk_ready = Signal(str)
    recording_started = Signal()
    recording_stopped = Signal(object)
    model_status = Signal(str, str)
    error = Signal(str)


class GigaFlowController(QObject):
    def __init__(self, app: QApplication):
        super().__init__()
        self.app = app
        self.paths = ensure_app_dirs()
        self.config_path = self.paths["root"] / "config.json"
        self.config = AppConfig.load(self.config_path)
        self.config.save(self.config_path)
        self.store = HistoryStore(self.paths["root"] / "history.sqlite3")
        self.bridge = EventBridge()
        self.overlay = ListeningOverlay()
        self.window = MainWindow(self.config, self.store)
        self.setup_dialog = ModelSetupDialog()
        self.recorder = AudioRecorder(self.bridge.level.emit)
        self.engine = TranscriptionEngine(
            self.config.model_name,
            self.paths["models"] / self.config.model_name,
            self.config.quantization,
            self.bridge.model_status.emit,
        )
        self.hotkey = GlobalHotkey(self.config.hotkey, self.bridge.hotkey.emit)
        self.started_at = 0.0
        self.processing = False
        self.model_ready = False
        self.runtime_started = False
        self.shutting_down = False
        self._opening_microphone = False
        self._stopping_recording = False
        self._committed_samples = 0
        self._chunk_texts: list[str] = []
        self._typed_text = ""
        self._stream_broken = False
        self._target_window: int | None = None
        self.partial_timer = QTimer(self)
        self.partial_timer.setInterval(self.config.partial_interval_ms)
        self.partial_timer.timeout.connect(self._request_partial)
        self.silence_timer = QTimer(self)
        self.silence_timer.setInterval(200)
        self.silence_timer.timeout.connect(self._check_auto_finish)

        self.bridge.hotkey.connect(self.toggle_recording)
        self.bridge.level.connect(self.overlay.set_level)
        self.bridge.transcription.connect(self._on_transcription)
        self.bridge.chunk_ready.connect(self._on_chunk_ready)
        self.bridge.recording_started.connect(self._on_recording_started)
        self.bridge.recording_stopped.connect(self._on_recording_stopped)
        self.bridge.model_status.connect(self._on_model_status)
        self.bridge.error.connect(self._on_error)
        self.overlay.set_saved_position(self.config.overlay_x, self.config.overlay_y)
        self.overlay.position_changed.connect(self._save_overlay_position)
        self.window.toggle_requested.connect(self.toggle_recording)
        self.window.config_changed.connect(self._save_config)
        self.window.hotkey_capture_started.connect(self.hotkey.unregister)
        self.window.hotkey_changed.connect(self._apply_hotkey)
        self.setup_dialog.start_requested.connect(self._finish_startup)
        self.setup_dialog.retry_requested.connect(self._retry_model_download)
        self.setup_dialog.cancelled.connect(self.shutdown)

        self.tray = QSystemTrayIcon(application_icon(), self)
        self.tray.setToolTip("GigaFlow")
        menu = QMenu()
        show_action = QAction("Открыть GigaFlow", menu)
        show_action.triggered.connect(self.show_window)
        toggle_action = QAction("Начать / завершить диктовку", menu)
        toggle_action.triggered.connect(self.toggle_recording)
        quit_action = QAction("Выйти", menu)
        quit_action.triggered.connect(self.shutdown)
        menu.addAction(show_action)
        menu.addAction(toggle_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)

    def start(self) -> None:
        self.setup_dialog.set_downloading(
            "Проверяем модель распознавания",
            "Пожалуйста, подождите. При первом запуске модель будет загружена автоматически.",
        )
        self.setup_dialog.show()
        self.setup_dialog.raise_()
        self.setup_dialog.activateWindow()
        self.engine.preload()

    @Slot()
    def _finish_startup(self) -> None:
        if not self.model_ready or self.runtime_started:
            return
        self.runtime_started = True
        self.setup_dialog.finish_and_hide()
        try:
            self.hotkey.register()
        except Exception as exc:
            self.window.set_status("Горячая клавиша недоступна", str(exc))
        self.tray.show()
        self.show_window()

    @Slot()
    def _retry_model_download(self) -> None:
        if self.model_ready:
            self.setup_dialog.set_ready()
            return
        self.setup_dialog.set_downloading(
            "Повторная загрузка модели",
            "Пожалуйста, подождите. GigaFlow автоматически продолжит подготовку.",
        )
        self.engine.preload()

    @Slot()
    def show_window(self) -> None:
        if not self.runtime_started:
            self.setup_dialog.show()
            self.setup_dialog.raise_()
            self.setup_dialog.activateWindow()
            return
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()

    @Slot()
    def toggle_recording(self) -> None:
        if not self.runtime_started or not self.model_ready:
            self.show_window()
            return
        if self.recorder.recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self) -> None:
        if self.processing:
            self.window.set_status(
                "Ещё распознаю предыдущую запись",
                "Подождите несколько секунд",
            )
            return
        if self._opening_microphone:
            return
        self._opening_microphone = True
        self.window.set_status("Открываю микрофон", "Секунду…")
        threading.Thread(
            target=self._open_microphone,
            args=(self.config.microphone,),
            name="GigaFlow-MicOpen",
            daemon=True,
        ).start()

    def _open_microphone(self, device: int | None) -> None:
        # sounddevice/PortAudio can block for a while opening a device (a
        # slow USB/Bluetooth mic, or one held by another app under WASAPI
        # exclusive mode). Doing this off the Qt thread keeps the window,
        # tray and global hotkey responsive instead of freezing GigaFlow.
        try:
            self.recorder.start(device)
        except Exception as exc:
            self._opening_microphone = False
            self.bridge.error.emit(f"Не удалось открыть микрофон: {exc}")
            return
        self.bridge.recording_started.emit()

    @Slot()
    def _on_recording_started(self) -> None:
        self._opening_microphone = False
        self._committed_samples = 0
        self._chunk_texts = []
        self._typed_text = ""
        self._stream_broken = False
        # Captured once, before "recognizing" work runs, so a later window
        # switch during that gap can't cause text to land in the wrong app.
        self._target_window = foreground_external_window()
        self.started_at = time.monotonic()
        self.window.set_recording(True)
        self.window.set_status(
            "Слушаю",
            "Закончите говорить — пауза автоматически завершит запись",
        )
        self.overlay.show_listening()
        self.partial_timer.start()
        self.silence_timer.start()

    def _stop_recording(self) -> None:
        if self._stopping_recording or not self.recorder.recording:
            return
        self._stopping_recording = True
        self.partial_timer.stop()
        self.silence_timer.stop()
        self.overlay.show_processing()
        self.processing = True
        self.window.set_status("Распознаю", "Готовый текст будет скопирован автоматически")
        # Closing the stream can block briefly too; keep it off the Qt thread
        # for the same reason as opening it.
        threading.Thread(
            target=self._close_and_submit,
            name="GigaFlow-MicClose",
            daemon=True,
        ).start()

    def _close_and_submit(self) -> None:
        audio = self.recorder.stop()
        self.bridge.recording_stopped.emit(audio)

    @Slot(object)
    def _on_recording_stopped(self, audio: np.ndarray) -> None:
        self._stopping_recording = False
        self.window.set_recording(False)
        if audio.size < SAMPLE_RATE // 2 and not self._chunk_texts:
            self.processing = False
            self.overlay.show_error("Слишком короткая запись")
            self.window.set_status("Запись слишком короткая", "Попробуйте ещё раз")
            return
        remainder = audio[self._committed_samples :]
        if remainder.size >= SAMPLE_RATE // 2:
            self.engine.submit(
                remainder,
                final=True,
                callback=self.bridge.transcription.emit,
                error_callback=self.bridge.error.emit,
            )
        else:
            self.bridge.transcription.emit("", True)

    def _request_partial(self) -> None:
        if not self.recorder.recording:
            return
        audio = self.recorder.snapshot()
        self._maybe_commit_chunk(audio)
        if not self.config.show_partial_text:
            return
        tail = audio[self._committed_samples :]
        if tail.size < SAMPLE_RATE // 2:
            return
        accepted = self.engine.submit(
            tail,
            final=False,
            callback=self.bridge.transcription.emit,
            error_callback=self.bridge.error.emit,
        )
        if accepted:
            self.overlay.show_recognizing()

    def _maybe_commit_chunk(self, audio: np.ndarray) -> None:
        # Recognize and insert audio in fixed-size chunks as soon as they are
        # long enough, instead of waiting for the whole dictation to finish
        # before anything is typed. Each chunk is recognized once and never
        # revisited, so growing the transcript can only append text.
        chunk_samples = int(self.config.stream_chunk_seconds * SAMPLE_RATE)
        if audio.size - self._committed_samples < chunk_samples:
            return
        start = self._committed_samples
        end = start + chunk_samples
        self._committed_samples = end
        self.engine.submit(
            audio[start:end],
            final=True,
            callback=lambda text, final: self.bridge.chunk_ready.emit(text),
            error_callback=self.bridge.error.emit,
        )

    @Slot(str)
    def _on_chunk_ready(self, text: str) -> None:
        if not self.recorder.recording and not self.processing:
            return
        cleaned = remove_filler_words(text, self.config.filler_filter) if text else ""
        if not cleaned:
            return
        self._chunk_texts.append(cleaned)
        self._apply_stream_text(merge_transcripts(self._chunk_texts))

    def _apply_stream_text(self, full_text: str) -> None:
        if self._stream_broken or not self._target_window or full_text == self._typed_text:
            return
        old = self._typed_text
        prefix = common_prefix_length(old, full_text)
        if prefix < len(old) and not send_backspaces(self._target_window, len(old) - prefix):
            self._stream_broken = True
            return
        suffix = full_text[prefix:]
        if suffix and not type_text(self._target_window, suffix):
            self._stream_broken = True
            return
        self._typed_text = full_text

    def _check_auto_finish(self) -> None:
        if not self.recorder.recording or not self.recorder.heard_voice:
            return
        if time.monotonic() - self.started_at < 1.0:
            return
        if self.recorder.silence_seconds >= self.config.auto_finish_silence_seconds:
            self._stop_recording()

    @Slot(str, bool)
    def _on_transcription(self, text: str, final: bool) -> None:
        # A final callback is the one irreversible action in a dictation
        # session: it writes to the clipboard and may paste into another app.
        # Ignore any duplicate/stale final callback after that session has
        # completed so text can never be automatically pasted twice.
        if final and not self.processing:
            return
        if not final:
            if text and self.recorder.recording:
                preview = merge_transcripts([*self._chunk_texts, text])
                self.overlay.set_partial(preview)
            return
        remainder = remove_filler_words(text, self.config.filler_filter) if text else ""
        if remainder:
            self._chunk_texts.append(remainder)
        full_text = merge_transcripts(self._chunk_texts)
        self._apply_stream_text(full_text)
        if not full_text:
            self.processing = False
            self._on_error("Речь не распознана")
            return
        duration = max(0.0, time.monotonic() - self.started_at)
        self.processing = False
        copied = copy_text(full_text)
        typed_live = (
            bool(self._target_window)
            and not self._stream_broken
            and self._typed_text == full_text
        )
        pasted = typed_live or (copied and paste_from_clipboard(self._target_window))
        self.store.add(full_text, duration)
        self.window.refresh_history()
        if pasted:
            self.window.set_status("Вставлено", "Текст автоматически вставлен в активное окно")
            self.overlay.show_result("Вставлено • " + full_text, "Вставлено")
        elif copied:
            self.window.set_status("Скопировано", "Поставьте курсор и нажмите Ctrl+V")
            self.overlay.show_result("Ctrl+V — вставить • " + full_text)
        else:
            self.window.set_status(
                "Текст сохранён в истории",
                "Буфер Windows занят — выберите запись и нажмите «Скопировать»",
            )
            self.overlay.show_error("Буфер занят — текст сохранён")
        self.tray.showMessage(
            "GigaFlow",
            (
                "Текст распознан и вставлен"
                if pasted
                else "Текст распознан и скопирован"
                if copied
                else "Текст сохранён в истории"
            ),
            (
                QSystemTrayIcon.MessageIcon.Information
                if copied
                else QSystemTrayIcon.MessageIcon.Warning
            ),
            1800,
        )

    @Slot(str, str)
    def _on_model_status(self, title: str, detail: str) -> None:
        self.window.set_status(title, detail)
        if title == "Модель готова":
            self.model_ready = True
            self.setup_dialog.set_ready(
                "Модель распознавания загружена и проверена. Можно начинать работу."
            )
        elif title.startswith("Не удалось"):
            self.model_ready = False
            self.setup_dialog.set_error(
                detail
                or "Проверьте подключение к интернету и нажмите «Повторить загрузку»."
            )
            self.show_window()
        else:
            self.setup_dialog.set_downloading(title, detail)

    @Slot(str)
    def _on_error(self, message: str) -> None:
        logging.error(message)
        self.processing = False
        friendly = message
        if "download" in message.lower() or "huggingface" in message.lower():
            friendly = "Не удалось загрузить модель. Проверьте интернет и повторите."
        self.overlay.show_error(friendly)
        self.window.set_recording(False)
        self.window.set_status("Ошибка", friendly)
        self.show_window()

    @Slot()
    def _save_config(self) -> None:
        self.config.save(self.config_path)

    @Slot(int, int)
    def _save_overlay_position(self, x: int, y: int) -> None:
        self.config.overlay_x = x
        self.config.overlay_y = y
        self.config.save(self.config_path)

    @Slot(str)
    def _apply_hotkey(self, value: str) -> None:
        self.config.hotkey = value
        self.config.save(self.config_path)
        try:
            self.hotkey.hotkey = self.config.hotkey
            self.hotkey.register()
            self.window.set_status(
                "Настройки сохранены",
                f"{self.config.hotkey} — начать или завершить",
            )
        except Exception as exc:
            self.window.set_status("Не удалось назначить клавишу", str(exc))

    def _tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_window()

    @Slot()
    def shutdown(self) -> None:
        if self.shutting_down:
            return
        self.shutting_down = True
        self.partial_timer.stop()
        self.silence_timer.stop()
        if self.recorder.recording:
            self.recorder.cancel()
        self.hotkey.unregister()
        self.engine.close()
        self.store.close()
        self.tray.hide()
        self.app.quit()


def configure_logging(log_dir: Path) -> None:
    logging.basicConfig(
        filename=log_dir / "gigaflow.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        encoding="utf-8",
    )


def main() -> int:
    if "--check-install" in sys.argv:
        # CI/package smoke check: exercise packaged imports and writable user
        # paths without opening the microphone or downloading the model.
        if sys.stdout is None or sys.stderr is None:
            raise RuntimeError("Windowed launcher did not initialize output streams")
        import onnx_asr  # noqa: F401
        import sounddevice  # noqa: F401

        ensure_app_dirs()
        return 0

    instance = SingleInstanceGuard()
    if not instance.acquire():
        return 0
    try:
        set_windows_app_id()
        QApplication.setQuitOnLastWindowClosed(False)
        app = QApplication(sys.argv)
        app.setApplicationName("GigaFlow")
        app.setOrganizationName("GigaFlow")
        app.setStyleSheet(APP_STYLE)
        app.setWindowIcon(application_icon())
        paths = ensure_app_dirs()
        configure_logging(paths["logs"])
        controller = GigaFlowController(app)
        app.aboutToQuit.connect(controller.hotkey.unregister)
        controller.start()
        return app.exec()
    finally:
        instance.release()
