from obs_keeper.config import MonitorConfig, RemediationConfig
from obs_keeper.detector import (
    LOST, RECOVERED, REMEDIATE, REMINDER, REASON_NO_DATA, REASON_SILENCE, SilenceDetector,
)

LOUD, QUIET = -20.0, -91.0


def make(inputs=(), silence_seconds=60, threshold=-70.0, repeat=30, ignore_muted=True, remediation=None):
    monitor = MonitorConfig(
        inputs=list(inputs), silence_seconds=silence_seconds,
        silence_threshold_db=threshold, ignore_muted=ignore_muted,
    )
    return SilenceDetector(monitor, repeat, remediation or RemediationConfig())


def feed(detector, name, db, start, end, step=1.0):
    """Feed samples every ``step`` s in [start, end); return every transition, evaluating each step."""
    out, t = [], start
    while t < end:
        out += detector.on_sample(name, db, t)
        out += detector.evaluate(t)
        t += step
    return out


def kinds(transitions):
    return [t.kind for t in transitions]


def test_inactive_detector_ignores_everything():
    d = make()
    assert d.on_sample("a", QUIET, 0) == []
    assert d.evaluate(1000) == []
    assert d.snapshot(1000) == []


def test_sound_keeps_input_ok():
    d = make()
    d.set_active(True, 0)
    assert feed(d, "a", LOUD, 0, 500) == []
    assert not d.any_lost()


def test_silence_alerts_once_after_the_window():
    d = make(silence_seconds=60, repeat=1000)
    d.set_active(True, 0)
    feed(d, "a", LOUD, 0, 10)
    out = feed(d, "a", QUIET, 10, 200)
    assert kinds(out) == [LOST]
    lost = out[0]
    assert lost.reason == REASON_SILENCE
    assert 60 <= lost.silent_for < 62  # last signal at t=9, alert at t=69..70
    assert d.any_lost()


def test_threshold_boundary_is_not_signal():
    d = make(threshold=-70.0, silence_seconds=10)
    d.set_active(True, 0)
    assert kinds(feed(d, "a", -70.0, 0, 30)) == [LOST]


def test_reminders_repeat_while_lost():
    d = make(silence_seconds=10, repeat=30)
    d.set_active(True, 0)
    out = feed(d, "a", QUIET, 0, 100)
    assert kinds(out) == [LOST, REMINDER, REMINDER]


def test_recovery_on_first_loud_sample_and_state_reset():
    d = make(silence_seconds=10)
    d.set_active(True, 0)
    feed(d, "a", QUIET, 0, 20)
    out = d.on_sample("a", LOUD, 20)
    assert kinds(out) == [RECOVERED]
    assert 19 <= out[0].silent_for <= 21
    assert not d.any_lost()
    assert feed(d, "a", QUIET, 21, 25) == []  # a fresh window starts from the recovery


def test_no_samples_at_all_is_caught_with_no_data_reason():
    d = make(inputs=["a"], silence_seconds=60, repeat=10_000)
    d.set_active(True, 0)
    out = [t for now in range(0, 100) for t in d.evaluate(now)]
    assert kinds(out) == [LOST]
    assert out[0].reason == REASON_NO_DATA


def test_input_that_stops_reporting_mid_recording_is_no_data():
    d = make(silence_seconds=60, repeat=10_000)
    d.set_active(True, 0)
    feed(d, "a", LOUD, 0, 30)
    out = [t for now in range(30, 200) for t in d.evaluate(now)]
    assert kinds(out) == [LOST]
    assert out[0].reason == REASON_NO_DATA


def test_stale_loud_value_does_not_hide_a_dead_input():
    # the weakness of level-polling scripts: last value stays "loud" forever
    d = make(silence_seconds=30)
    d.set_active(True, 0)
    d.on_sample("a", LOUD, 5)
    assert kinds([t for now in range(6, 60) for t in d.evaluate(now)]) == [LOST]


def test_only_configured_inputs_are_watched():
    d = make(inputs=["mic"], silence_seconds=10)
    d.set_active(True, 0)
    d.on_sample("desktop", QUIET, 1)
    out = [t for now in range(0, 40) for t in d.evaluate(now)]
    assert [t.input_name for t in out] == ["mic"]
    assert [s.name for s in d.snapshot(40)] == ["mic"]


def test_auto_tracking_starts_from_first_sample():
    d = make(silence_seconds=10)
    d.set_active(True, 0)
    d.on_sample("a", QUIET, 100)  # first seen at t=100, grace starts there
    assert d.evaluate(105) == []
    assert kinds(d.evaluate(111)) == [LOST]


def test_activation_resets_state_and_grants_grace():
    d = make(inputs=["a"], silence_seconds=10)
    d.set_active(True, 0)
    d.evaluate(0)
    assert kinds([t for now in range(1, 20) for t in d.evaluate(now)]) == [LOST]
    d.set_active(False, 20)
    assert d.evaluate(21) == [] and not d.any_lost()
    d.set_active(True, 100)  # e.g. a new recording
    assert d.evaluate(105) == []
    assert kinds(d.evaluate(111)) == [LOST]


def test_muted_input_never_alerts_and_clears_lost():
    d = make(inputs=["a"], silence_seconds=10)
    d.set_active(True, 0)
    assert kinds([t for now in range(0, 15) for t in d.evaluate(now)]) == [LOST]
    d.set_muted("a", True, 15)
    assert d.evaluate(16) == [] and not d.any_lost()
    assert [t for now in range(16, 200) for t in d.evaluate(now)] == []
    d.set_muted("a", False, 200)
    assert d.evaluate(205) == []  # fresh window after unmute
    assert kinds(d.evaluate(211)) == [LOST]


def test_mute_state_known_before_the_watch_exists():
    d = make(inputs=["a"], silence_seconds=10)
    d.set_muted("a", True, 0)  # arrives on connect, recording not started yet
    d.set_active(True, 1)
    assert [t for now in range(1, 100) for t in d.evaluate(now)] == []


def test_muted_input_alerts_when_ignore_muted_is_off():
    d = make(inputs=["a"], silence_seconds=10, ignore_muted=False)
    d.set_muted("a", True, 0)
    d.set_active(True, 0)
    assert kinds([t for now in range(0, 15) for t in d.evaluate(now)]) == [LOST]


def test_each_input_is_independent():
    d = make(silence_seconds=10)
    d.set_active(True, 0)
    out = []
    for now in range(0, 30):
        out += d.on_sample("desktop", LOUD, now)
        out += d.on_sample("mic", QUIET, now)
        out += d.evaluate(now)
    assert [(t.kind, t.input_name) for t in out] == [(LOST, "mic")]


def test_remediation_after_delay_limited_attempts_and_cooldown():
    rem = RemediationConfig(enabled=True, after_seconds=20, max_attempts=2, cooldown_seconds=50)
    d = make(silence_seconds=10, repeat=10_000, remediation=rem)
    d.set_active(True, 0)
    out = feed(d, "a", QUIET, 0, 300)
    attempts = [t for t in out if t.kind == REMEDIATE]
    assert [t.attempt for t in attempts] == [1, 2]
    # lost at ~t=10; first heal >= 20 s later, second >= 50 s after the first
    assert attempts[0].silent_for >= 30
    assert attempts[1].silent_for - attempts[0].silent_for >= 50


def test_remediation_disabled_by_default():
    d = make(silence_seconds=10)
    d.set_active(True, 0)
    assert REMEDIATE not in kinds(feed(d, "a", QUIET, 0, 600))


def test_remediation_budget_resets_after_recovery():
    rem = RemediationConfig(enabled=True, after_seconds=5, max_attempts=1, cooldown_seconds=1)
    d = make(silence_seconds=10, repeat=10_000, remediation=rem)
    d.set_active(True, 0)
    assert kinds(feed(d, "a", QUIET, 0, 60)).count(REMEDIATE) == 1
    d.on_sample("a", LOUD, 60)
    assert kinds(feed(d, "a", QUIET, 61, 200)).count(REMEDIATE) == 1


def test_configure_changes_thresholds_live_and_keeps_state():
    d = make(inputs=["a"], silence_seconds=100)
    d.set_active(True, 0)
    assert [t for now in range(0, 50) for t in d.evaluate(now)] == []
    d.configure(MonitorConfig(inputs=["a"], silence_seconds=30), 30, RemediationConfig(), 50)
    assert kinds(d.evaluate(51)) == [LOST]  # silent since t=0, new window is 30 s


def test_snapshot_reports_level_and_state():
    d = make(silence_seconds=10)
    d.set_active(True, 0)
    d.on_sample("a", -33.0, 1)
    snap = d.snapshot(4)[0]
    assert (snap.name, snap.peak_db, snap.muted, snap.lost) == ("a", -33.0, False, False)
    assert snap.silent_for == 3


# ---- early warning (icon turns red before the alert fires) ----

def make_warn(warn=20, silence=180, **kw):
    monitor = MonitorConfig(inputs=kw.pop("inputs", []), silence_seconds=silence, warn_seconds=warn,
                            ignore_muted=kw.pop("ignore_muted", True))
    return SilenceDetector(monitor, 120, RemediationConfig())


def test_warning_appears_after_warn_seconds_long_before_the_alert():
    d = make_warn(warn=20, silence=180)
    d.set_active(True, 0)
    d.on_sample("a", QUIET, 0)
    assert not d.any_warning(19)
    assert d.any_warning(20)
    assert d.snapshot(20)[0].warning
    assert d.evaluate(20) == []  # no alert yet: the warning is visual only
    assert not d.any_lost()


def test_warning_gives_way_to_lost_and_clears_on_sound():
    d = make_warn(warn=20, silence=60)
    d.set_active(True, 0)
    d.on_sample("a", QUIET, 0)
    d.evaluate(60)
    assert d.any_lost() and not d.any_warning(61)
    d.on_sample("a", LOUD, 62)
    assert not d.any_lost() and not d.any_warning(63)


def test_no_warning_when_muted_or_inactive():
    d = make_warn()
    d.set_muted("a", True, 0)
    d.set_active(True, 0)
    d.on_sample("a", QUIET, 0)
    assert not d.any_warning(500)
    d.set_active(False, 501)
    assert not d.any_warning(1000)


def test_warn_seconds_is_capped_by_the_alert_window():
    d = make_warn(warn=100, silence=30)
    d.set_active(True, 0)
    d.on_sample("a", QUIET, 0)
    assert d.any_warning(30)


def test_warning_is_per_input():
    d = make_warn(warn=20)
    d.set_active(True, 0)
    for now in range(0, 40):
        d.on_sample("desktop", LOUD, now)
        d.on_sample("mic", QUIET, now)
    warned = [s.name for s in d.snapshot(40) if s.warning]
    assert warned == ["mic"]
