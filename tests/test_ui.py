import pytest

from obs_keeper import alerts
from obs_keeper.config import Config
from obs_keeper.detector import InputSnapshot
from obs_keeper.monitor import CONNECTED, Monitor, Status
from obs_keeper.ui.app import TrayController
from obs_keeper.ui.main_window import MainWindow


@pytest.fixture(autouse=True)
def system_lists(monkeypatch):
    monkeypatch.setattr(alerts, "available_sounds", lambda: ["Glass", "Sosumi"])
    monkeypatch.setattr(alerts, "available_voices", lambda: ["Milena", "Samantha"])


class Recorder:
    def __init__(self):
        self.saved, self.passwords = [], []

    def save(self, config):
        self.saved.append(config)

    def store_password(self, password):
        self.passwords.append(password)


@pytest.fixture
def env(qapp):
    config, rec = Config(), Recorder()
    monitor = Monitor(config, lambda: "")
    monitor._known_inputs = [("Desktop", "screen_capture"), ("Mic", "coreaudio_input_capture")]
    applied, reconnects = [], []
    monitor.apply_config = applied.append
    monitor.reconnect = lambda: reconnects.append(1)
    window = MainWindow(monitor, config, save=rec.save, store_password=rec.store_password)
    window.applied, window.reconnects, window.rec = applied, reconnects, rec
    yield window
    window._quitting = True
    window.close()


def test_default_config_roundtrips_through_widgets(env):
    assert env.to_config() == Config()


def test_every_setting_is_editable_and_saved(env):
    env.host.setText("10.0.0.5")
    env.port.setValue(4466)
    env.selected_inputs.setChecked(True)
    env.inputs_list.item(1).setCheckState(env.inputs_list.item(1).checkState().__class__.Checked)
    env.threshold.setValue(-55)
    env.silence_window.setValue(90)
    env.only_recording.setChecked(False)
    env.include_streaming.setChecked(True)
    env.ignore_muted.setChecked(False)
    env.notification.setChecked(False)
    env.sound_name.setCurrentText("Glass")
    env.speech.setChecked(True)
    env.voice.setCurrentIndex(env.voice.findData("Milena"))
    env.repeat.setValue(45)
    env.notify_recovery.setChecked(False)
    env.heal_enabled.setChecked(True)
    env.heal_after.setValue(12)
    env.heal_attempts.setValue(3)
    env.heal_cooldown.setValue(99)
    env.language.setCurrentIndex(env.language.findData("ru"))
    assert env.save()
    cfg = env.rec.saved[-1]
    assert (cfg.obs.host, cfg.obs.port) == ("10.0.0.5", 4466)
    assert cfg.monitor.inputs == ["Mic"]
    assert (cfg.monitor.silence_threshold_db, cfg.monitor.silence_seconds) == (-55.0, 90)
    assert (cfg.monitor.only_while_recording, cfg.monitor.include_streaming, cfg.monitor.ignore_muted) == (False, True, False)
    assert (cfg.alerts.notification, cfg.alerts.sound_name, cfg.alerts.speech, cfg.alerts.speech_voice) == (False, "Glass", True, "Milena")
    assert (cfg.alerts.repeat_seconds, cfg.alerts.notify_recovery) == (45, False)
    assert (cfg.remediation.enabled, cfg.remediation.after_seconds, cfg.remediation.max_attempts, cfg.remediation.cooldown_seconds) == (True, 12, 3, 99)
    assert cfg.language == "ru"
    assert env.applied == [cfg]
    assert env.current_config == cfg


def test_all_inputs_option_saves_an_empty_list(env):
    env.selected_inputs.setChecked(True)
    env.inputs_list.item(0).setCheckState(env.inputs_list.item(0).checkState().__class__.Checked)
    env.all_inputs.setChecked(True)
    env.save()
    assert env.rec.saved[-1].monitor.inputs == []


def test_invalid_values_are_not_saved(env):
    env.silence_window.setValue(5)
    env.repeat.setValue(10)
    env.threshold.setValue(0)
    assert env.save()  # boundary values are valid
    env.rec.saved.clear()
    env._config.language = "auto"
    env.silence_window.setMinimum(1)
    env.silence_window.setValue(1)
    assert not env.save()
    assert env.rec.saved == []
    assert "silence_seconds" in env.message.text()


def test_password_goes_to_the_keychain_not_the_config(env):
    env.password.setText("hunter2")
    assert env.save()
    assert env.rec.passwords == ["hunter2"]
    assert env.password.text() == ""
    assert env.reconnects == [1]
    assert "hunter2" not in repr(env.rec.saved[-1])


def test_empty_password_field_keeps_the_stored_password(env):
    env.save()
    assert env.rec.passwords == [] and env.reconnects == []


def test_revert_restores_saved_values(env):
    env.threshold.setValue(-33)
    env.revert_button.click()
    assert env.threshold.value() == -70


def test_language_switch_retranslates_everything(env):
    assert env.tabs.tabText(0) == "Status" and env.save_button.text() == "Save"
    env.language.setCurrentIndex(env.language.findData("ru"))
    env.save()
    assert env.tabs.tabText(0) == "Состояние"
    assert env.save_button.text() == "Сохранить"
    assert env.windowTitle() == "OBS Keeper"
    assert env.voice.itemText(0) == "Системный по умолчанию"
    assert env.silence_window.suffix() == " с"
    env.language.setCurrentIndex(env.language.findData("en"))
    env.save()
    assert env.tabs.tabText(0) == "Status"


def test_missing_sound_and_offline_inputs_are_kept(qapp):
    config = Config()
    config.alerts.sound_name = "Vanished"
    config.monitor.inputs = ["Old input"]
    window = MainWindow(Monitor(config, lambda: ""), config, save=lambda c: None, store_password=lambda p: None)
    assert window.sound_name.currentText() == "Vanished"
    assert window.selected_inputs.isChecked()
    assert window.to_config().monitor.inputs == ["Old input"]  # OBS is offline, but the choice survives


def test_live_panel_builds_rows_and_shows_state(env):
    env.show()
    status = Status(
        connection=CONNECTED, recording=True, watching=True, alerting=True,
        inputs=[InputSnapshot("Desktop", -91.0, 200.0, False, True, "silence")],
    )
    env.refresh(status, {"Desktop": -91.0, "Mic": -30.0})
    assert sorted(env._rows) == ["Desktop", "Mic"]
    assert "SILENT" in env._rows["Desktop"].state.text()
    assert env._rows["Mic"].state.text() == "Watching"
    assert env._rows["Mic"].db.text() == "-30 dB"
    assert not env.no_levels.isVisible()
    env.refresh(Status(), {})
    assert env._rows == {} and env.no_levels.isVisible()


def test_input_list_follows_obs_and_keeps_ticks(env):
    env.selected_inputs.setChecked(True)
    env.inputs_list.item(1).setCheckState(env.inputs_list.item(1).checkState().__class__.Checked)
    env._monitor._known_inputs = [("Desktop", "x"), ("Mic", "x"), ("Camera", "x")]
    env.refresh(Status(connection=CONNECTED), {})
    names = [env.inputs_list.item(i).text() for i in range(env.inputs_list.count())]
    assert names == ["Desktop", "Mic", "Camera"]
    assert env.to_config().monitor.inputs == ["Mic"]


def test_closing_hides_but_quit_really_quits(env):
    quits = []
    env.quit_requested.connect(lambda: quits.append(1))
    env.show()
    env.close()
    assert not env.isVisible() and quits == []
    env.quit_button.click()
    assert quits == [1]


def test_bottom_bar_only_on_settings_tabs(env):
    env.show()
    assert not env.bottom.isVisible()
    env.tabs.setCurrentIndex(2)
    assert env.bottom.isVisible()


def test_tray_click_opens_window_and_tooltip_follows_state(env):
    from PySide6.QtWidgets import QSystemTrayIcon

    tray = TrayController(env)
    tray.update(Status(), "en")
    assert tray.tray.toolTip() == "OBS Keeper: not connected to OBS"
    tray.update(Status(connection=CONNECTED, watching=True, alerting=True), "ru")
    assert tray.tray.toolTip() == "OBS Keeper: ПРОПАЛ ЗВУК"
    assert tray.quit_action.text() == "Выйти из OBS Keeper"
    assert not env.isVisible()
    tray._on_activated(QSystemTrayIcon.ActivationReason.Trigger)
    assert env.isVisible()


# ---- issues found in manual testing ----

def test_open_restores_a_minimized_window(env, qapp):
    tray = TrayController(env)
    env.show()
    env.showMinimized()
    qapp.processEvents()
    assert env.isMinimized()
    tray.show_window()
    qapp.processEvents()
    assert env.isVisible() and not env.isMinimized()


def test_open_menu_action_and_any_click_but_context_open_the_window(env, qapp):
    from PySide6.QtWidgets import QSystemTrayIcon

    tray = TrayController(env)
    reasons = QSystemTrayIcon.ActivationReason
    for reason in (reasons.Trigger, reasons.DoubleClick, reasons.MiddleClick):
        env.hide()
        tray._on_activated(reason)
        assert env.isVisible(), reason
    env.showMinimized()
    qapp.processEvents()
    tray.open_action.trigger()
    qapp.processEvents()
    assert env.isVisible() and not env.isMinimized()


def test_tray_icon_blinks_only_while_silent(env):
    tray = TrayController(env)
    tray.update(Status(connection=CONNECTED, watching=True, warning=True), "en")
    assert tray._blink.isActive()
    assert tray.tray.toolTip() == "OBS Keeper: no sound for a while"
    before = tray.tray.icon().cacheKey()
    tray._toggle_blink()
    assert tray.tray.icon().cacheKey() != before
    tray.update(Status(connection=CONNECTED, watching=True, alerting=True), "en")
    assert tray._blink.isActive()
    tray.update(Status(connection=CONNECTED, watching=True), "en")
    assert not tray._blink.isActive()


def test_new_settings_are_editable_and_saved(env):
    env.warn_window.setValue(30)
    env.sound_seconds.setValue(45)
    env.silence_window.setValue(120)
    assert env.save()
    cfg = env.rec.saved[-1]
    assert (cfg.monitor.warn_seconds, cfg.alerts.sound_seconds, cfg.monitor.silence_seconds) == (30, 45, 120)


def test_unsaved_changes_are_flagged_and_cleared_by_save_or_revert(env):
    env.show()
    assert not env.dirty_label.isVisible()
    env.warn_window.setValue(33)
    env._update_dirty()
    assert env.dirty_label.isVisible()
    env.revert_button.click()
    assert not env.dirty_label.isVisible()
    env.password.setText("x")
    env._update_dirty()
    assert env.dirty_label.isVisible()
    env.save()
    assert not env.dirty_label.isVisible()


def test_settings_file_location_is_shown(qapp, tmp_path):
    config = Config()
    target = tmp_path / "cfg" / "config.json"
    window = MainWindow(Monitor(config, lambda: ""), config, save=lambda c: None,
                        store_password=lambda p: None, config_file=target)
    assert window.config_location.text() == str(target)


def test_activate_app_never_raises():
    from obs_keeper.ui.macos import activate_app

    activate_app()
