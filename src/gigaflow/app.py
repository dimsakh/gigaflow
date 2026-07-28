from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal, Slot
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from .audio import AudioRecorder, SAMPLE_RATE
from .clipboard import copy_text, foreground_external_window, paste_from_clipboard
from .config import AppConfig
from .hotkeys import GlobalHotkey
from .icons import application_icon, set_windows_app_id
from .paths import ensure_app_dirs
from .storage import HistoryStore
from .text import remove_filler_words
from .transcriber import TranscriptionEngine
from .ui.main_window import MainWindow
from .ui.overlay import ListeningOverlay
from .ui.theme import APP_STYLE


class EventBridge(QObject):
    hotkey = Signal()
    level = Signal(float)
    transcription = Signal(str, bool)
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
        self.recorder = AudioRecorder(self.bridge.level.emit)
        self.engine = TranscriptionEngine(
            self.config.model_name,
            self.paths["models"] / self.config.model_name,
            self.config.quantization,
        )
        self.engine.preload()
        self.hotkey = GlobalHotkey(self.config.hotkey, self.bridge.hotkey.emit)
        self.started_at = 0.0
        self.processing = False
        self.partial_timer = QTimer(self)
        self.partial_timer.setInterval(self.config.partial_interval_ms)
        self.partial_timer.timeout.connect(self._request_partial)
        self.silence_timer = QTimer(self)
        self.silence_timer.setInterval(200)
        self.silence_timer.timeout.connect(self._check_auto_finish)

        self.bridge.hotkey.connect(self.toggle_recording)
        self.bridge.level.connect(self.overlay.set_level)
        self.bridge.transcription.connect(self._on_transcription)
        self.bridge.error.connect(self._on_error)
        self.window.toggle_requested.connect(self.toggle_recording)
        self.window.config_changed.connect(self._save_config)
        self.window.hotkey_capture_started.connect(self.hotkey.unregister)
        self.window.hotkey_changed.connect(self._apply_hotkey)

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
        try:
            self.hotkey.register()
        except Exception as exc:
            self.window.set_status("Горячая клавиша недоступна", str(exc))
        self.tray.show()
        if not self.config.start_minimized:
            self.show_window()

    @Slot()
    def show_window(self) -> None:
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()

    @Slot()
    def toggle_recording(self) -> None:
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
        try:
            self.recorder.start(self.config.microphone)
        except Exception as exc:
            self._on_error(f"Не удалось открыть микрофон: {exc}")
            return
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
        self.partial_timer.stop()
        self.silence_timer.stop()
        audio = self.recorder.stop()
        self.window.set_recording(False)
        if audio.size < SAMPLE_RATE // 2:
            self.overlay.show_error("Слишком короткая запись")
            self.window.set_status("Запись слишком короткая", "Попробуйте ещё раз")
            return
        self.overlay.show_processing()
        self.processing = True
        self.window.set_status("Распознаю", "Готовый текст будет скопирован автоматически")
        self.engine.submit(
            audio,
            final=True,
            callback=self.bridge.transcription.emit,
            error_callback=self.bridge.error.emit,
        )

    def _request_partial(self) -> None:
        if not self.config.show_partial_text or not self.recorder.recording:
            return
        audio = self.recorder.snapshot()
        accepted = self.engine.submit(
            audio,
            final=False,
            callback=self.bridge.transcription.emit,
            error_callback=self.bridge.error.emit,
        )
        if accepted:
            self.overlay.show_recognizing()

    def _check_auto_finish(self) -> None:
        if not self.recorder.recording or not self.recorder.heard_voice:
            return
        if time.monotonic() - self.started_at < 1.0:
            return
        if self.recorder.silence_seconds >= self.config.auto_finish_silence_seconds:
            self._stop_recording()

    @Slot(str, bool)
    def _on_transcription(self, text: str, final: bool) -> None:
        if final:
            text = remove_filler_words(text, self.config.filler_filter)
        if not text:
            if final:
                self._on_error("Речь не распознана")
            return
        if not final:
            if self.recorder.recording:
                self.overlay.set_partial(text)
            return
        duration = max(0.0, time.monotonic() - self.started_at)
        self.processing = False
        copied = copy_text(text)
        pasted = copied and paste_from_clipboard(foreground_external_window())
        self.store.add(text, duration)
        self.window.refresh_history()
        if pasted:
            self.window.set_status("Вставлено", "Текст автоматически вставлен в активное окно")
            self.overlay.show_result("Вставлено • " + text, "Вставлено")
        elif copied:
            self.window.set_status("Скопировано", "Поставьте курсор и нажмите Ctrl+V")
            self.overlay.show_result("Ctrl+V — вставить • " + text)
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
