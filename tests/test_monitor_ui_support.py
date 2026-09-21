import threading
import time

from obs_keeper import alerts
from obs_keeper.alerts import AlertDispatcher, available_voices
from obs_keeper.config import Config
from obs_keeper.monitor import Monitor
from obs_keeper.obs_client import ObsError, _LockedRequests


class Clock:
    now = 100.0

    def __call__(self):
        return self.now


def make():
    clock = Clock()
    config = Config()
    monitor = Monitor(config, lambda: "", dispatcher=AlertDispatcher(config.alerts, "en", runner=lambda c: None), clock=clock)
    return monitor, clock


def test_take_levels_returns_the_peak_since_the_last_call():
    monitor, clock = make()
    for db in (-50.0, -12.0, -40.0):
        monitor._on_meters([("Desktop", db)])
    assert monitor.take_levels() == {"Desktop": -12.0}
    monitor._on_meters([("Desktop", -60.0)])
    assert monitor.take_levels() == {"Desktop": -60.0}


def test_take_levels_marks_inputs_that_stopped_reporting():
    monitor, clock = make()
    monitor._on_meters([("Desktop", -20.0)])
    monitor.take_levels()
    clock.now += 10
    assert monitor.take_levels() == {"Desktop": None}


def test_levels_are_collected_even_when_not_watching():
    monitor, _ = make()
    assert not monitor.status().watching
    monitor._on_meters([("Mic", -33.0)])
    assert monitor.take_levels() == {"Mic": -33.0}


def test_status_reports_muted_inputs():
    monitor, clock = make()
    monitor._on_mute("Mic", True)
    assert monitor.status().muted == frozenset({"Mic"})


def test_reconnect_cuts_the_retry_wait():
    attempts = []

    def refuse(host, port, password, sink):
        attempts.append(time.time())
        raise ObsError("refused")

    monitor = Monitor(Config(), lambda: "", connect=refuse)
    monitor.start()
    deadline = time.time() + 3
    while time.time() < deadline and not attempts:
        time.sleep(0.01)
    monitor.reconnect()
    deadline = time.time() + 3
    while time.time() < deadline and len(attempts) < 2:
        time.sleep(0.01)
    monitor.stop()
    assert len(attempts) >= 2
    assert attempts[1] - attempts[0] < 2  # far below the 5 s retry pause


def test_requests_from_two_threads_never_overlap():
    class Slow:
        def __init__(self):
            self.inside = 0
            self.max_inside = 0

        def get_version(self):
            self.inside += 1
            self.max_inside = max(self.max_inside, self.inside)
            time.sleep(0.01)
            self.inside -= 1

    slow = Slow()
    locked = _LockedRequests(slow)
    threads = [threading.Thread(target=lambda: [locked.get_version() for _ in range(5)]) for _ in range(4)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert slow.max_inside == 1


def test_available_voices_parses_say_output(monkeypatch):
    class Result:
        stdout = (
            "Albert              en_US    # Hello! My name is Albert.\n"
            "Bad News            en_US    # Hello! My name is Bad News.\n"
            "Milena              ru_RU    # Здравствуйте! Меня зовут Милена.\n"
            "garbage line\n"
        )

    monkeypatch.setattr(alerts.subprocess, "run", lambda *a, **k: Result())
    assert available_voices() == ["Albert", "Bad News", "Milena"]


def test_available_voices_survives_a_missing_binary(monkeypatch):
    def boom(*a, **k):
        raise FileNotFoundError

    monkeypatch.setattr(alerts.subprocess, "run", boom)
    assert available_voices() == []
