from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QKeySequenceEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..audio import input_devices
from ..clipboard import copy_text
from ..config import AppConfig
from ..storage import Dictation, HistoryStore


class MainWindow(QMainWindow):
    toggle_requested = Signal()
    config_changed = Signal()
    hotkey_capture_started = Signal()
    hotkey_changed = Signal(str)

    def __init__(self, config: AppConfig, store: HistoryStore):
        super().__init__()
        self.config = config
        self.store = store
        self.setWindowTitle("GigaFlow")
        self.resize(920, 650)
        self.setMinimumSize(760, 530)
        self._device_map: list[int | None] = []
        self._build_ui()
        self.refresh_devices()
        self.refresh_history()

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(30, 26, 30, 28)
        layout.setSpacing(18)

        title_row = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("GigaFlow")
        title.setObjectName("title")
        subtitle = QLabel("Локальный голосовой ввод на базе GigaAM‑v3")
        subtitle.setObjectName("muted")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        title_row.addLayout(title_box)
        title_row.addStretch()
        self.record_button = QPushButton("Начать диктовку")
        self.record_button.clicked.connect(self.toggle_requested)
        title_row.addWidget(self.record_button)
        layout.addLayout(title_row)

        status_card = QFrame()
        status_card.setObjectName("card")
        status_layout = QHBoxLayout(status_card)
        status_layout.setContentsMargins(20, 16, 20, 16)
        self.status_label = QLabel("Готово к работе")
        self.status_label.setObjectName("section")
        self.status_detail = QLabel("Ctrl+Shift+Space — начать • пауза завершит запись")
        self.status_detail.setObjectName("muted")
        status_text = QVBoxLayout()
        status_text.addWidget(self.status_label)
        status_text.addWidget(self.status_detail)
        status_layout.addLayout(status_text)
        status_layout.addStretch()
        layout.addWidget(status_card)

        settings_card = QFrame()
        settings_card.setObjectName("card")
        settings_layout = QHBoxLayout(settings_card)
        settings_layout.setContentsMargins(18, 14, 18, 14)

        mic_box = QVBoxLayout()
        mic_label = QLabel("Микрофон")
        mic_label.setObjectName("muted")
        self.mic_combo = QComboBox()
        self.mic_combo.currentIndexChanged.connect(self._microphone_changed)
        mic_box.addWidget(mic_label)
        mic_box.addWidget(self.mic_combo)
        settings_layout.addLayout(mic_box, 2)

        key_box = QVBoxLayout()
        key_label = QLabel("Горячая клавиша — нажмите поле, затем сочетание")
        key_label.setObjectName("muted")
        self.hotkey_edit = QKeySequenceEdit()
        self.hotkey_edit.setMaximumSequenceLength(1)
        self.hotkey_edit.setClearButtonEnabled(True)
        self.hotkey_edit.setKeySequence(
            QKeySequence.fromString(
                self.config.hotkey,
                QKeySequence.SequenceFormat.PortableText,
            )
        )
        self.hotkey_edit.installEventFilter(self)
        self.hotkey_edit.editingFinished.connect(self._hotkey_changed)
        key_box.addWidget(key_label)
        key_box.addWidget(self.hotkey_edit)
        settings_layout.addLayout(key_box, 1)

        cleanup_box = QVBoxLayout()
        cleanup_label = QLabel("Очистка слов-паразитов")
        cleanup_label.setObjectName("muted")
        self.cleanup_combo = QComboBox()
        self.cleanup_combo.addItem("Выключена", "off")
        self.cleanup_combo.addItem("Мягкая", "soft")
        self.cleanup_combo.addItem("Полная", "full")
        cleanup_index = self.cleanup_combo.findData(self.config.filler_filter)
        self.cleanup_combo.setCurrentIndex(max(0, cleanup_index))
        self.cleanup_combo.currentIndexChanged.connect(self._cleanup_changed)
        cleanup_box.addWidget(cleanup_label)
        cleanup_box.addWidget(self.cleanup_combo)
        settings_layout.addLayout(cleanup_box, 1)
        layout.addWidget(settings_card)

        history_row = QHBoxLayout()
        heading = QLabel("История")
        heading.setObjectName("section")
        history_row.addWidget(heading)
        history_row.addStretch()
        copy_button = QPushButton("Скопировать")
        copy_button.setObjectName("secondary")
        copy_button.clicked.connect(self.copy_selected)
        history_row.addWidget(copy_button)
        delete_button = QPushButton("Удалить")
        delete_button.setObjectName("danger")
        delete_button.clicked.connect(self.delete_selected)
        history_row.addWidget(delete_button)
        layout.addLayout(history_row)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Время", "Длина", "Текст"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.doubleClicked.connect(self.copy_selected)
        layout.addWidget(self.table, 1)

    def refresh_devices(self) -> None:
        self.mic_combo.blockSignals(True)
        self.mic_combo.clear()
        self._device_map = [None]
        self.mic_combo.addItem("Системный микрофон")
        try:
            for device_id, name in input_devices():
                self._device_map.append(device_id)
                self.mic_combo.addItem(name)
        except Exception:
            pass
        if self.config.microphone in self._device_map:
            self.mic_combo.setCurrentIndex(self._device_map.index(self.config.microphone))
        self.mic_combo.blockSignals(False)

    def refresh_history(self) -> None:
        items = self.store.recent()
        self.table.setRowCount(len(items))
        for row, item in enumerate(items):
            local_time = datetime.fromisoformat(item.created_at).strftime("%d.%m %H:%M")
            time_item = QTableWidgetItem(local_time)
            time_item.setData(Qt.ItemDataRole.UserRole, item.id)
            self.table.setItem(row, 0, time_item)
            self.table.setItem(row, 1, QTableWidgetItem(f"{item.duration_seconds:.1f} с"))
            self.table.setItem(row, 2, QTableWidgetItem(item.text))

    def selected(self) -> tuple[int, str] | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        return (
            int(self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)),
            self.table.item(row, 2).text(),
        )

    def copy_selected(self) -> None:
        selected = self.selected()
        if selected:
            if copy_text(selected[1]):
                self.set_status("Скопировано", "Теперь можно нажать Ctrl+V")
            else:
                self.set_status("Буфер Windows занят", "Попробуйте ещё раз")

    def delete_selected(self) -> None:
        selected = self.selected()
        if selected:
            self.store.delete(selected[0])
            self.refresh_history()

    def _microphone_changed(self, index: int) -> None:
        if 0 <= index < len(self._device_map):
            self.config.microphone = self._device_map[index]
            self.config_changed.emit()

    def _cleanup_changed(self, index: int) -> None:
        mode = self.cleanup_combo.itemData(index)
        if mode:
            self.config.filler_filter = str(mode)
            self.config_changed.emit()

    def _hotkey_changed(self) -> None:
        value = self.hotkey_edit.keySequence().toString(
            QKeySequence.SequenceFormat.PortableText
        )
        value = value.strip().lower().replace("meta", "windows")
        if not value:
            value = self.config.hotkey
            self.hotkey_edit.setKeySequence(
                QKeySequence.fromString(
                    value,
                    QKeySequence.SequenceFormat.PortableText,
                )
            )
        self.hotkey_changed.emit(value)

    def eventFilter(self, watched, event) -> bool:
        if watched is self.hotkey_edit and event.type() == QEvent.Type.FocusIn:
            self.hotkey_capture_started.emit()
        return super().eventFilter(watched, event)

    def set_recording(self, recording: bool) -> None:
        self.record_button.setText("Завершить" if recording else "Начать диктовку")

    def set_status(self, title: str, detail: str) -> None:
        self.status_label.setText(title)
        self.status_detail.setText(detail)

    def closeEvent(self, event) -> None:
        event.ignore()
        self.hide()
