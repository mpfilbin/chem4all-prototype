from __future__ import annotations
import datetime
from PyQt6.QtCore import Qt, QRect
from PyQt6.QtGui import QColor, QFont, QPixmap, QPainter
from PyQt6.QtWidgets import QWidget, QApplication

_BG = QColor("#1b3a5c")
_WHITE = QColor("#ffffff")
_LIGHT = QColor("#8ab4d4")
_DIM = QColor("#5d849e")
_STATUS = QColor("#aacce0")

W, H = 480, 260


def _make_pixmap() -> QPixmap:
    pix = QPixmap(W, H)
    pix.fill(_BG)

    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    title_font = QFont()
    title_font.setPointSize(48)
    title_font.setWeight(QFont.Weight.Bold)
    p.setFont(title_font)
    p.setPen(_WHITE)
    p.drawText(QRect(0, 40, W, 90), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, "Chem4All")

    tag_font = QFont()
    tag_font.setPointSize(12)
    p.setFont(tag_font)
    p.setPen(_LIGHT)
    p.drawText(QRect(0, 130, W, 32), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, "Making chemistry accessible")

    copy_font = QFont()
    copy_font.setPointSize(9)
    p.setFont(copy_font)
    p.setPen(_DIM)
    year = datetime.date.today().year
    p.drawText(QRect(0, H - 28, W, 20), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, f"© {year} Michael Filbin. All rights reserved.")

    p.end()
    return pix


class _SplashWindow(QWidget):
    """Frameless top-level widget used as a splash screen.

    QSplashScreen on macOS uses an NSPanel window level that is hidden when the
    app loses focus.  A plain QWidget with FramelessWindowHint + WindowStaysOnTopHint
    maps to a normal window level and stays visible across app switches.
    """

    def __init__(self, pixmap: QPixmap) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self._pixmap = pixmap
        self._msg = ""
        self._msg_color = _STATUS
        self.setFixedSize(pixmap.size())

    def show(self) -> None:
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.geometry()
            self.move(geo.center() - self.rect().center())
        super().show()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.drawPixmap(0, 0, self._pixmap)
        if self._msg:
            p.setPen(self._msg_color)
            font = QFont()
            font.setPointSize(9)
            p.setFont(font)
            p.drawText(
                QRect(0, H - 48, W, 20),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                self._msg,
            )
        p.end()

    def showMessage(self, msg: str, alignment=None, color: QColor | None = None) -> None:
        self._msg = msg
        if color is not None:
            self._msg_color = color
        self.repaint()

    def finish(self, _window: QWidget) -> None:
        self.close()


def make_splash() -> _SplashWindow:
    return _SplashWindow(_make_pixmap())


def splash_message(splash: _SplashWindow, msg: str) -> None:
    splash.showMessage(
        msg,
        Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter,
        _STATUS,
    )
