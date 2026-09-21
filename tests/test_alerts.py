import pytest

from obs_keeper import alerts
from obs_keeper.alerts import AlertDispatcher, notification_command, speech_command
from obs_keeper.config import AlertConfig
from obs_keeper.detector import LOST, RECOVERED, REMEDIATE, REMINDER, REASON_NO_DATA, Transition


@pytest.fixture(autouse=True)
def fake_sounds(monkeypatch):
    monkeypatch.setattr(alerts, "available_sounds", lambda: ["Glass", "Sosumi"])


def dispatch(transition, language="en", max_attempts=2, **cfg):
    sent = []
    AlertDispatcher(AlertConfig(**cfg), language, runner=sent.append).handle(transition, max_attempts)
    return sent


def test_lost_uses_notification_and_sound():
    sent = dispatch(Transition(LOST, "Desktop Audio", 185))
    assert [c[0] for c in sent] == ["osascript", "afplay"]
    assert "Desktop Audio" in sent[0][-2] and "3 min 05 s" in sent[0][-2]
    assert sent[0][-1] == "OBS: audio lost"
    assert sent[1] == ["afplay", "/System/Library/Sounds/Sosumi.aiff"]


def test_reminder_uses_its_own_title():
    assert dispatch(Transition(REMINDER, "a", 300))[0][-1] == "OBS: audio is still missing"


def test_no_data_reason_changes_wording():
    text = dispatch(Transition(LOST, "a", 60, REASON_NO_DATA))[0][-2]
    assert "stopped sending audio" in text


def test_russian_text():
    sent = dispatch(Transition(LOST, "Звук", 65), language="ru")
    assert sent[0][-1] == "OBS: пропал звук"
    assert "1 мин 05 с" in sent[0][-2]


def test_speech_channel():
    sent = dispatch(Transition(LOST, "a", 60), speech=True, speech_voice="Milena", sound=False, notification=False)
    assert sent == [["say", "-v", "Milena", "--", "OBS: audio lost. “a” has been silent for 1 min 00 s."]]


def test_recovery_is_quiet_and_can_be_disabled():
    sent = dispatch(Transition(RECOVERED, "a", 400))
    assert [c[0] for c in sent] == ["osascript"]  # no sound for good news
    assert dispatch(Transition(RECOVERED, "a", 400), notify_recovery=False) == []


def test_remediation_notice_mentions_attempt():
    sent = dispatch(Transition(REMEDIATE, "a", 90, attempt=1), max_attempts=2)
    assert "attempt 1 of 2" in sent[0][-2]
    assert len(sent) == 1


def test_channels_can_be_switched_off():
    assert dispatch(Transition(LOST, "a", 60), notification=False, sound=False) == []


def test_unknown_sound_is_skipped_instead_of_running_a_path():
    sent = dispatch(Transition(LOST, "a", 60), notification=False, sound_name="../../etc/passwd")
    assert sent == []


def test_notification_text_is_argv_not_applescript_source():
    nasty = 'x" & (do shell script "rm -rf ~") & "'
    command = notification_command("t", nasty)
    assert nasty not in "".join(command[:-2])
    assert command[-2] == nasty


def test_unsafe_voice_names_are_dropped():
    assert speech_command("hi", "-o /tmp/x") == ["say", "--", "hi"]
    assert speech_command("-v hi", "") == ["say", "--", "-v hi"]


def test_send_test_is_loud():
    sent = []
    AlertDispatcher(AlertConfig(), "en", runner=sent.append).send_test()
    assert [c[0] for c in sent] == ["osascript", "afplay"]


# ---- long alert sound ----

import threading
import time

from obs_keeper.alerts import SoundPlayer


def test_sound_is_played_for_the_configured_duration():
    plays = []

    class Player:
        def play(self, command, seconds): plays.append((command, seconds))
        def stop(self): plays.append("stop")

    AlertDispatcher(AlertConfig(sound_seconds=25), "en", runner=lambda c: None, sound=Player()).handle(
        Transition(LOST, "a", 60))
    assert plays == [(["afplay", "/System/Library/Sounds/Sosumi.aiff"], 25)]


def test_sound_stops_when_audio_returns():
    plays = []

    class Player:
        def play(self, command, seconds): plays.append("play")
        def stop(self): plays.append("stop")

    d = AlertDispatcher(AlertConfig(), "en", runner=lambda c: None, sound=Player())
    d.handle(Transition(LOST, "a", 60))
    d.handle(Transition(RECOVERED, "a", 90))
    assert plays == ["play", "stop"]


class FakeProc:
    def __init__(self, length):
        self._end = time.monotonic() + length
        self.terminated = False

    def poll(self):
        return 0 if self.terminated or time.monotonic() >= self._end else None

    def terminate(self): self.terminated = True
    def wait(self): pass


class FakePopen:
    def __init__(self, length=0.1):
        self.procs, self.length = [], length

    def __call__(self, command, **kw):
        proc = FakeProc(self.length)
        self.procs.append(proc)
        return proc


def test_sound_player_repeats_until_the_deadline():
    popen = FakePopen(0.1)
    SoundPlayer(popen=popen).play(["afplay", "x"], 0.45)
    time.sleep(0.9)
    assert 3 <= len(popen.procs) <= 6
    assert not any(p.terminated for p in popen.procs)  # the last one plays out, it is not cut


def test_sound_player_stop_cuts_the_current_sound_and_ends_the_loop():
    popen = FakePopen(5)
    player = SoundPlayer(popen=popen)
    player.play(["afplay", "x"], 60)
    time.sleep(0.15)
    player.stop()
    time.sleep(0.3)
    assert len(popen.procs) == 1 and popen.procs[0].terminated


def test_a_new_alert_replaces_the_previous_sound():
    popen = FakePopen(5)
    player = SoundPlayer(popen=popen)
    player.play(["afplay", "x"], 60)
    time.sleep(0.15)
    player.play(["afplay", "y"], 60)
    time.sleep(0.3)
    assert popen.procs[0].terminated and not popen.procs[1].terminated
    player.stop()


def test_missing_afplay_does_not_crash():
    def broken(*a, **k):
        raise FileNotFoundError

    SoundPlayer(popen=broken).play(["afplay", "x"], 1)
    time.sleep(0.1)


def test_create_wires_the_looping_player():
    assert isinstance(AlertDispatcher.create(AlertConfig(), "en")._sound, SoundPlayer)
