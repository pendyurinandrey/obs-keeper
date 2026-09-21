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
