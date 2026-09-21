from obs_keeper.config import Config
from obs_keeper.detector import InputSnapshot
from obs_keeper.monitor import CONNECTED, CONNECTING, DISCONNECTED, Status
from obs_keeper.ui.state import ALERT, IDLE, OFFLINE, WATCHING, input_state, tray_state


def status(**kw):
    kw.setdefault("connection", CONNECTED)
    return Status(**kw)


def snap(name="a", silent_for=0.0, lost=False, reason="silence"):
    return InputSnapshot(name, -30.0, silent_for, False, lost, reason)


def test_tray_state():
    assert tray_state(status(connection=DISCONNECTED)) == OFFLINE
    assert tray_state(status(connection=CONNECTING)) == OFFLINE
    assert tray_state(status()) == IDLE
    assert tray_state(status(watching=True)) == WATCHING
    assert tray_state(status(watching=True, alerting=True)) == ALERT


def test_input_state_waiting_watching_quiet_lost():
    cfg = Config()
    assert input_state("a", status(), cfg, "en") == ("Waiting for recording", "ok")
    st = status(watching=True, inputs=[snap(silent_for=1)])
    assert input_state("a", st, cfg, "en") == ("Watching", "ok")
    st = status(watching=True, inputs=[snap(silent_for=45)])
    assert input_state("a", st, cfg, "en") == ("Quiet for 45 s", "warn")
    st = status(watching=True, alerting=True, inputs=[snap(silent_for=190, lost=True)])
    assert input_state("a", st, cfg, "en") == ("SILENT for 3 min 10 s", "bad")
    st = status(watching=True, alerting=True, inputs=[snap(silent_for=190, lost=True, reason="no_data")])
    assert input_state("a", st, cfg, "ru") == ("НЕТ ДАННЫХ 3 мин 10 с", "bad")


def test_muted_and_unwatched_inputs():
    cfg = Config()
    st = status(watching=True, muted=frozenset({"a"}), inputs=[snap(lost=True)])
    assert input_state("a", st, cfg, "en") == ("Muted", "ok")
    cfg.monitor.inputs = ["other"]
    assert input_state("a", status(watching=True), cfg, "en") == ("Not watched", "ok")


def test_warning_state_and_row_text():
    from obs_keeper.ui.state import WARNING

    st = status(watching=True, warning=True, inputs=[
        InputSnapshot("a", -91.0, 25.0, False, False, "silence", warning=True)])
    assert tray_state(st) == WARNING
    assert input_state("a", st, Config(), "en") == ("Quiet for 25 s", "bad")
    assert tray_state(status(watching=True, warning=True, alerting=True)) == ALERT  # alert wins
