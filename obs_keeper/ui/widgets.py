"""Small custom widgets and painted icons."""

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget

from obs_keeper.ui.state import ALERT, IDLE, OFFLINE, WATCHING

MIN_DB, MAX_DB = -90.0, 0.0

GREEN, AMBER, RED, GREY = QColor("#34c759"), QColor("#ff9f0a"), QColor("#ff3b30"), QColor("#8e8e93")


class LevelBar(QWidget):
    """Horizontal peak meter (-90..0 dBFS) with a marker at the silence threshold."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._db: float | None = None
        self._threshold = -70.0
        self._lost = False
        self.setMinimumSize(160, 14)

    def set_level(self, db: float | None, threshold: float, lost: bool) -> None:
        if (db, threshold, lost) != (self._db, self._threshold, self._lost):
            self._db, self._threshold, self._lost = db, threshold, lost
            self.update()

    @staticmethod
    def _x(db: float, width: float) -> float:
        return (min(max(db, MIN_DB), MAX_DB) - MIN_DB) / (MAX_DB - MIN_DB) * width

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 2.5, -0.5, -2.5)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.palette().mid())
        painter.drawRoundedRect(rect, 3, 3)
        if self._db is not None:
            color = RED if self._lost else (GREEN if self._db > self._threshold else AMBER)
            painter.setBrush(color)
            fill = QRectF(rect)
            fill.setWidth(max(self._x(self._db, rect.width()), 0.0))
            painter.drawRoundedRect(fill, 3, 3)
        marker = rect.left() + self._x(self._threshold, rect.width())
        painter.setPen(QPen(self.palette().windowText().color(), 1.5))
        painter.drawLine(int(marker), int(rect.top()) - 2, int(marker), int(rect.bottom()) + 2)


_TRAY_COLORS = {ALERT: RED, WATCHING: GREEN, IDLE: GREY, OFFLINE: AMBER}
_TRAY_GLYPHS = {ALERT: "!", OFFLINE: "–"}


def tray_icon(state: str) -> QIcon:
    """Menu-bar icon whose *shape* differs per state, not only its colour:
    solid disc = watching, ring = connected but idle, "!" = audio lost, "–" = no connection."""
    color = _TRAY_COLORS[state]
    size = 44
    pixmap = QPixmap(size, size)
    pixmap.setDevicePixelRatio(2.0)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    if state == IDLE:
        painter.setPen(QPen(color, 4))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(4, 4, size - 8, size - 8)
    else:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(2, 2, size - 4, size - 4)
    glyph = _TRAY_GLYPHS.get(state)
    if glyph:
        font = QFont()
        font.setBold(True)
        font.setPixelSize(int(size * 0.62))
        painter.setFont(font)
        painter.setPen(QColor("white"))
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, glyph)
    painter.end()
    return QIcon(pixmap)
