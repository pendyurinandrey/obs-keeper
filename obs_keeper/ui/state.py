"""Qt-free UI decisions, so they can be tested without a display."""

from obs_keeper.config import Config
from obs_keeper.detector import REASON_NO_DATA, InputSnapshot
from obs_keeper.i18n import format_duration, tr
from obs_keeper.monitor import CONNECTED, Status

ALERT, WARNING, WATCHING, IDLE, OFFLINE = "alert", "warning", "watching", "idle", "offline"

# A quiet input is only worth mentioning once it has been quiet for a while.
QUIET_NOTE_AFTER_SECONDS = 5.0


def tray_state(status: Status) -> str:
    if status.connection != CONNECTED:
        return OFFLINE
    if status.alerting:
        return ALERT
    if status.warning:
        return WARNING
    return WATCHING if status.watching else IDLE


def input_state(name: str, status: Status, config: Config, language: str) -> tuple[str, str]:
    """``(text, severity)`` for one row of the live panel; severity is ``ok``, ``warn`` or ``bad``."""
    if name in status.muted:
        return tr("ui.input.muted", language), "ok"
    if config.monitor.inputs and name not in config.monitor.inputs:
        return tr("ui.input.not_watched", language), "ok"
    if not status.watching:
        return tr("ui.input.waiting", language), "ok"
    snapshot: InputSnapshot | None = next((s for s in status.inputs if s.name == name), None)
    if snapshot is None:
        return tr("ui.input.watching", language), "ok"
    duration = format_duration(snapshot.silent_for, language)
    if snapshot.lost:
        key = "ui.input.no_data" if snapshot.reason == REASON_NO_DATA else "ui.input.lost"
        return tr(key, language, duration=duration), "bad"
    if snapshot.warning:
        return tr("ui.input.quiet", language, duration=duration), "bad"
    if snapshot.silent_for >= QUIET_NOTE_AFTER_SECONDS:
        return tr("ui.input.quiet", language, duration=duration), "warn"
    return tr("ui.input.watching", language), "ok"
