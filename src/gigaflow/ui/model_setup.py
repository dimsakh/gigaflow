from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)


class ModelSetupDialog(QDialog):
    """Blocks normal application startup until the speech model is ready."""

    start_requested = Signal()
    retry_requested = Signal()
    cancelled = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._retry_mode = False
        self._allow_close = False

        self.setWindowTitle("GigaFlow — подготовка")
        self.setModal(True)
        self.setMinimumSize(520, 280)
        self.setMaximumWidth(680)

        title = QLabel("Подготовка GigaFlow")
        title.setObjectName("setupTitle")
        title.setStyleSheet("font-size: 24px; font-weight: 700;")

        self.status = QLabel("Проверяем модель распознавания")
        self.status.setStyleSheet("font-size: 17px; font-weight: 600;")

        self.detail = QLabel(
            "Пожалуйста, подождите. При первом запуске загрузка может занять несколько минут."
        )
        self.detail.setWordWrap(True)
        self.detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setMinimumHeight(18)
        self.progress.setRange(0, 0)

        self.action_button = QPushButton("Загрузка…")
        self.action_button.setMinimumHeight(44)
        self.action_button.setEnabled(False)
        self.action_button.clicked.connect(self._on_action)

        hint = QLabel(
            "Не закрывайте GigaFlow до завершения загрузки. Диктовка станет доступна после подготовки модели."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #9ca3af;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(16)
        layout.addWidget(title)
        layout.addWidget(self.status)
        layout.addWidget(self.detail)
        layout.addWidget(self.progress)
        layout.addStretch(1)
        layout.addWidget(hint)
        layout.addWidget(self.action_button)

    def set_downloading(self, title: str, detail: str) -> None:
        self._retry_mode = False
        self.status.setText(title or "Загрузка модели распознавания")
        self.detail.setText(
            detail
            or "Пожалуйста, подождите. При первом запуске это может занять несколько минут."
        )
        self.progress.setRange(0, 0)
        self.action_button.setText("Загрузка…")
        self.action_button.setEnabled(False)

    def set_ready(self, detail: str = "Модель загружена. GigaFlow готов к работе.") -> None:
        self._retry_mode = False
        self.status.setText("Всё установлено")
        self.detail.setText(detail)
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.action_button.setText("Начать работу")
        self.action_button.setEnabled(True)
        self.action_button.setFocus()

    def set_error(self, detail: str) -> None:
        self._retry_mode = True
        self.status.setText("Не удалось загрузить модель")
        self.detail.setText(
            detail
            or "Проверьте подключение к интернету и нажмите «Повторить загрузку»."
        )
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.action_button.setText("Повторить загрузку")
        self.action_button.setEnabled(True)
        self.action_button.setFocus()

    def finish_and_hide(self) -> None:
        self._allow_close = True
        self.hide()

    def _on_action(self) -> None:
        if self._retry_mode:
            self.retry_requested.emit()
        else:
            self.start_requested.emit()

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self._allow_close:
            self.cancelled.emit()
        event.accept()
