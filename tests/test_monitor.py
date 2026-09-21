import time

import pytest

from obs_keeper import alerts
from obs_keeper.alerts import AlertDispatcher
from obs_keeper.config import Config
from obs_keeper.monitor import CONNECTED, DISCONNECTED, Monitor
from obs_keeper.obs_client import ObsError


@pytest.fixture(autouse=True)
def fake_sounds(monkeypatch):
    monkeypatch.setattr(alerts, "available_sounds", lambda: ["Sosumi"])


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class FakeConn:
    def __init__(self):
        self.restarted = []
        self.toggled = 1

    def restart_source(self, name):
        self.restarted.append(name)
        return self.toggled


def make(**overrides):
    config = Config()
    config.monitor.silence_seconds = 60
    config.alerts.repeat_seconds = 30
    for key, value in overrides.items():
        section, _, attr = key.partition("__")
        setattr(getattr(config, section), attr, value)
    sent, clock = [], Clock()
    dispatcher = AlertDispatcher(config.alerts, "en", runner=sent.append)
    monitor = Monitor(config, lambda: "", connect=None, dispatcher=dispatcher, clock=clock)
    return monitor, sent, clock


def titles(sent):
    return [c[-1] for c in sent if c[0] == "osascript"]


def test_no_alerts_while_not_recording():
    monitor, sent, clock = make()
    monitor._on_meters([("Desktop", -91.0)])
    clock.now += 500
    monitor.tick()
    assert sent == []
    assert not monitor.status().watching


def test_silence_during_recording_alerts_then_recovers():
    monitor, sent, clock = make()
    monitor._on_record_state(True)
    monitor._on_meters([("Desktop", -20.0)])
    for _ in range(70):
        clock.now += 1
        monitor._on_meters([("Desktop", -91.0)])
        monitor.tick()
    assert titles(sent) == ["OBS: audio lost"]
    assert any(c[0] == "afplay" for c in sent)
    assert monitor.status().alerting

    monitor._on_meters([("Desktop", -15.0)])
    assert titles(sent)[-1] == "OBS: audio is back"
    assert not monitor.status().alerting


def test_recording_stop_disarms_and_clears():
    monitor, sent, clock = make()
    monitor._on_record_state(True)
    monitor._on_meters([("Desktop", -91.0)])
    clock.now += 100
    monitor.tick()
    assert monitor.status().alerting
    monitor._on_record_state(False)
    st = monitor.status()
    assert not st.watching and not st.alerting and st.inputs == []


def test_streaming_only_counts_when_enabled():
    monitor, _, _ = make()
    monitor._on_stream_state(True)
    assert not monitor.status().watching
    monitor, _, _ = make(monitor__include_streaming=True)
    monitor._on_stream_state(True)
    assert monitor.status().watching


def test_always_on_mode_needs_a_connection_not_recording():
    monitor, _, _ = make(monitor__only_while_recording=False)
    monitor._conn = FakeConn()
    monitor._on_record_state(False)
    assert monitor.status().watching


def test_mute_from_obs_silences_alerts():
    monitor, sent, clock = make()
    monitor._on_record_state(True)
    monitor._on_meters([("Mic", -91.0)])
    monitor._on_mute("Mic", True)
    clock.now += 500
    monitor.tick()
    assert sent == []


def test_self_healing_restarts_the_source_and_reports_it():
    monitor, sent, clock = make(remediation__enabled=True, remediation__after_seconds=10)
    conn = FakeConn()
    monitor._on_record_state(True)
    for _ in range(90):
        clock.now += 1
        monitor._on_meters([("Desktop", -91.0)])
        monitor.tick(conn)
    assert conn.restarted == ["Desktop"]  # lost at 60 s, heal at 70 s, cooldown blocks the 2nd try
    assert "OBS: restarting the source" in titles(sent)


def test_failed_restart_does_not_raise():
    monitor, _, clock = make(remediation__enabled=True, remediation__after_seconds=1)

    class Broken(FakeConn):
        def restart_source(self, name):
            raise RuntimeError("socket closed")

    monitor._on_record_state(True)
    monitor._on_meters([("Desktop", -91.0)])
    for _ in range(80):
        clock.now += 1
        monitor.tick(Broken())


def test_apply_config_changes_language_and_windows_live():
    monitor, sent, clock = make()
    monitor._on_record_state(True)
    monitor._on_meters([("Desktop", -91.0)])
    new = Config()
    new.monitor.silence_seconds = 10
    new.language = "ru"
    monitor.apply_config(new)
    clock.now += 20
    monitor.tick()
    assert "OBS: пропал звук" in titles(sent)


def test_unreachable_obs_is_reported_and_stop_is_prompt():
    def refuse(host, port, password, sink):
        raise ObsError("refused", "nope")

    config = Config()
    config.language = "en"
    monitor = Monitor(config, lambda: "", connect=refuse)
    monitor.start()
    deadline = time.time() + 3
    while time.time() < deadline and not monitor.status().error:
        time.sleep(0.02)
    status = monitor.status()
    assert status.connection == DISCONNECTED
    assert "Connection refused" in status.error
    started = time.time()
    monitor.stop()
    assert time.time() - started < 2


def test_connected_status_and_listener(monkeypatch):
    class Conn(FakeConn):
        def recording_active(self): return True
        def streaming_active(self): return False
        def muted_inputs(self): return set()
        def alive(self): return True
        def ping(self): pass
        def close(self): pass
        def list_inputs(self): return [("Desktop", "screen_capture")]

    conn = Conn()
    monitor = Monitor(Config(), lambda: "", connect=lambda *a: conn)
    seen = []
    monitor.add_listener(seen.append)
    monitor.start()
    deadline = time.time() + 4
    while time.time() < deadline and not (seen and seen[-1].connection == CONNECTED and seen[-1].watching):
        time.sleep(0.02)
    try:
        assert seen[-1].connection == CONNECTED and seen[-1].recording and seen[-1].watching
        assert monitor.list_inputs() == [("Desktop", "screen_capture")]
    finally:
        monitor.stop()
