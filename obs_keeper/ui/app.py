"""Application entry: menu-bar icon, main window, refresh timer."""

import logging
import os
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QLockFile, Qt, QTimer
from PySide6.QtGui import QAction, QCursor
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from obs_keeper.config import Config, config_path, load_config, save_config
from obs_keeper.credentials import get_password
from obs_keeper.i18n import resolve_language, tr
from obs_keeper.monitor import Monitor, Status
from obs_keeper.ui.main_window import MainWindow
from obs_keeper.ui.macos import activate_app
from obs_keeper.ui.state import OFFLINE, tray_state
from obs_keeper.ui.widgets import BLINKING, tray_icon

log = logging.getLogger(__name__)

REFRESH_MS = 150
BLINK_MS = 500


class TrayController:
    """The menu-bar icon. A click opens the window; a right/ctrl-click shows a small menu."""

    def __init__(self, window: MainWindow):
        self._window = window
        self._state: str | None = None
        self._lang: str | None = None
        self._bright = True
        self._blink = QTimer()
        self._blink.setInterval(BLINK_MS)
        self._blink.timeout.connect(self._toggle_blink)
        self.tray = QSystemTrayIcon(tray_icon(OFFLINE))
        self.menu = QMenu()
        self.open_action = QAction()
        self.quit_action = QAction()
        self.open_action.triggered.connect(self.show_window)
        self.quit_action.triggered.connect(window.request_quit)
        self.menu.addAction(self.open_action)
        self.menu.addSeparator()
        self.menu.addAction(self.quit_action)
        # No setContextMenu(): on macOS a context menu would swallow the plain click we want to
        # use for "open the app".
        self.tray.activated.connect(self._on_activated)

    def show(self) -> None:
        self.tray.show()

    def show_window(self) -> None:
        """Bring the window to the front, also when it is hidden, minimized or behind other apps."""
        window = self._window
        window.setWindowState((window.windowState() & ~Qt.WindowState.WindowMinimized) | Qt.WindowState.WindowActive)
        window.showNormal()  # plain show() leaves a minimized window minimized
        window.raise_()
        window.activateWindow()
        activate_app()

    def update(self, status: Status, lang: str) -> None:
        state = tray_state(status)
        if state != self._state:
            self._state = state
            self._bright = True
            self.tray.setIcon(tray_icon(state))
            if state in BLINKING:
                self._blink.start()
            else:
                self._blink.stop()
        self.tray.setToolTip(tr(f"ui.tray.{state}", lang))
        if lang != self._lang:
            self._lang = lang
            self.open_action.setText(tr("ui.menu.open", lang))
            self.quit_action.setText(tr("ui.menu.quit", lang))

    def _toggle_blink(self) -> None:
        self._bright = not self._bright
        self.tray.setIcon(tray_icon(self._state, self._bright))

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        log.debug("Tray activated: %s", reason)
        if reason == QSystemTrayIcon.ActivationReason.Context:
            self.menu.popup(QCursor.pos())
        else:  # any other click (left, double, middle) opens the app
            self.show_window()


def run_ui(path: Path | None = None) -> int:
    config: Config = load_config(path)
    lang = resolve_language(config.language)
    problems = config.validate()
    if problems:
        print(tr("cli.config_problems", lang), *problems, sep="\n  ", file=sys.stderr)
        return 2

    logging.basicConfig(
        level=logging.DEBUG if os.environ.get("OBS_KEEPER_DEBUG") else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    app = QApplication(sys.argv[:1])
    app.setApplicationName("OBS Keeper")
    app.setQuitOnLastWindowClosed(False)  # closing the window leaves the watchdog running

    lock = QLockFile(os.path.join(tempfile.gettempdir(), "obs-keeper.lock"))
    if not lock.tryLock(100):
        print(tr("ui.already_running", lang), file=sys.stderr)
        return 1

    target = path or config_path()
    monitor = Monitor(config, get_password)
    window = MainWindow(monitor, config, save=lambda cfg: save_config(cfg, target), config_file=target)
    tray = TrayController(window)
    window.quit_requested.connect(app.quit)

    def refresh() -> None:
        status = monitor.status()
        current = resolve_language(window.current_config.language)
        tray.update(status, current)
        if window.isVisible():
            window.refresh(status, monitor.take_levels())

    timer = QTimer()
    timer.setInterval(REFRESH_MS)
    timer.timeout.connect(refresh)

    monitor.start()
    tray.show()
    tray.show_window()
    timer.start()
    code = app.exec()
    timer.stop()
    monitor.stop()
    lock.unlock()
    return code
