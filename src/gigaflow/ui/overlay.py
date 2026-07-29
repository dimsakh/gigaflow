from __future__ import annotations

import math
import time
from collections import deque

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QApplication, QWidget


class ListeningOverlay(QWidget):
    position_changed = Signal(int, int)

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedSize(310, 74)
        self._levels: deque[float] = deque([0.05] * 16, maxlen=16)
        self._level = 0.0
        self._status = "Слушаю…"
        self._text = ""
        self._partial_seen = False
        self._started_at = time.monotonic()
        self._pulse = 0.0
        self._saved_position: QPoint | None = None
        self._drag_offset: QPoint | None = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(40)

    def show_listening(self) -> None:
        self._status = "Слушаю…"
        self._text = "Говорите • пауза завершит запись"
        self._partial_seen = False
        self._started_at = time.monotonic()
        self._position()
        self.show()
        self.update()

    def show_processing(self) -> None:
        self._status = "Распознаю…"
        self._text = "При первом запуске модель может загружаться"
        self._position()
        self.show()
        self.update()

    def show_result(self, text: str, status: str = "Скопировано") -> None:
        self._status = status
        self._text = text
        self._position()
        self.show()
        self.update()
        QTimer.singleShot(2400, self.hide)

    def show_error(self, text: str) -> None:
        self._status = "Не получилось"
        self._text = text
        self._position()
        self.show()
        self.update()

    def set_level(self, value: float) -> None:
        self._level = value

    def set_partial(self, text: str) -> None:
        if text:
            self._partial_seen = True
            self._status = "Текст онлайн"
            self._text = text
            self.update()

    def show_recognizing(self) -> None:
        if self._partial_seen:
            return
        self._status = "Распознаю…"
        self._text = "Формирую черновой текст…"
        self.update()

    def set_saved_position(self, x: int | None, y: int | None) -> None:
        if x is not None and y is not None:
            self._saved_position = QPoint(x, y)

    def _position(self) -> None:
        if self._saved_position is not None:
            self.move(self._saved_position)
            return
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        self.move(
            area.center().x() - self.width() // 2,
            area.bottom() - self.height() - 22,
        )

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            position = event.globalPosition().toPoint() - self._drag_offset
            self.move(position)
            self._saved_position = QPoint(position)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._drag_offset is not None:
            self._drag_offset = None
            self.unsetCursor()
            self._saved_position = self.pos()
            self.position_changed.emit(self.x(), self.y())
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _tick(self) -> None:
        self._pulse += 0.12
        wobble = 0.015 * (1 + math.sin(self._pulse))
        self._levels.append(max(0.025, min(1.0, self._level + wobble)))
        if self.isVisible():
            self.update()

    def paintEvent(self, event) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        shadow = QPainterPath()
        shadow.addRoundedRect(QRectF(4, 4, 302, 66), 17, 17)
        painter.fillPath(shadow, QColor(5, 8, 18, 235))
        painter.setPen(QPen(QColor(60, 72, 110), 1))
        painter.drawPath(shadow)

        indicator = QColor("#FF5577") if self._status == "Слушаю…" else QColor("#736BFF")
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(indicator)
        painter.drawEllipse(QPointF(19, 21), 4, 4)

        painter.setPen(QColor("#F2F4FF"))
        painter.setFont(QFont("Segoe UI", 8, QFont.Weight.DemiBold))
        painter.drawText(QRectF(29, 11, 82, 20), self._status)

        if self._status == "Слушаю…":
            elapsed = int(time.monotonic() - self._started_at)
            painter.setPen(QColor("#8E99B3"))
            painter.setFont(QFont("Segoe UI", 7))
            painter.drawText(
                QRectF(264, 11, 27, 18),
                Qt.AlignmentFlag.AlignRight,
                f"{elapsed // 60:02d}:{elapsed % 60:02d}",
            )

        base_x, base_y = 118.0, 21.0
        bar_width, gap = 3.0, 3.0
        for index, level in enumerate(self._levels):
            height = 3 + level * 19
            gradient = QColor("#6860FF")
            gradient.setAlpha(145 + int(level * 110))
            painter.setBrush(gradient)
            painter.drawRoundedRect(
                QRectF(base_x + index * (bar_width + gap), base_y - height / 2, bar_width, height),
                1.5,
                1.5,
            )

        painter.setPen(QColor("#C8D0E5"))
        painter.setFont(QFont("Segoe UI", 7))
        metrics = painter.fontMetrics()
        clipped = metrics.elidedText(
            self._text,
            Qt.TextElideMode.ElideLeft,
            270,
        )
        painter.drawText(
            QRectF(18, 40, 274, 20),
            Qt.AlignmentFlag.AlignVCenter,
            clipped,
        )
