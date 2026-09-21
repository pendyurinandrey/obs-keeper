"""The application window: live levels on the first tab, settings on the others."""

import copy
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMainWindow, QPushButton, QRadioButton, QScrollArea, QSpinBox,
    QTabWidget, QVBoxLayout, QWidget,
)

from obs_keeper import alerts as alerts_module
from obs_keeper import credentials
from obs_keeper.config import Config, save_config
from obs_keeper.i18n import resolve_language, tr
from obs_keeper.levels import SILENCE_FLOOR_DB
from obs_keeper.monitor import CONNECTED, CONNECTING, Monitor, Status
from obs_keeper.ui.state import input_state
from obs_keeper.ui.widgets import AMBER, GREEN, RED, LevelBar

SEVERITY_STYLE = {"ok": "", "warn": f"color: {AMBER.name()};", "bad": f"color: {RED.name()}; font-weight: 600;"}


class _Row:
    def __init__(self):
        self.name = QLabel()
        self.bar = LevelBar()
        self.db = QLabel()
        self.state = QLabel()
        self.db.setMinimumWidth(64)
        self.db.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

    def widgets(self):
        return self.name, self.bar, self.db, self.state


class MainWindow(QMainWindow):
    quit_requested = Signal()

    def __init__(
        self,
        monitor: Monitor,
        config: Config,
        save: Callable[[Config], Path] = save_config,
        store_password: Callable[[str], None] = credentials.set_password,
    ):
        super().__init__()
        self._monitor = monitor
        self._config = config
        self._save_config = save
        self._store_password = store_password
        self._lang = resolve_language(config.language)
        self._bindings: list[Callable[[str], None]] = []
        self._rows: dict[str, _Row] = {}
        self._known_inputs: list[str] = []
        self._quitting = False

        self.tabs = QTabWidget()
        self._build_status_tab()
        self._build_connection_tab()
        self._build_monitoring_tab()
        self._build_alerts_tab()
        self._build_healing_tab()
        self._build_general_tab()

        self.message = QLabel()
        self.revert_button, self.save_button = QPushButton(), QPushButton()
        self._t(self.revert_button.setText, "ui.btn.revert")
        self._t(self.save_button.setText, "ui.btn.save")
        self.revert_button.clicked.connect(lambda: self.load_from(self._config))
        self.save_button.clicked.connect(self.save)
        self.bottom = QWidget()
        bottom = QHBoxLayout(self.bottom)
        bottom.setContentsMargins(0, 0, 0, 0)
        bottom.addWidget(self.message, 1)
        bottom.addWidget(self.revert_button)
        bottom.addWidget(self.save_button)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addWidget(self.tabs)
        layout.addWidget(self.bottom)
        self.setCentralWidget(central)
        self.setMinimumSize(680, 540)
        self._t(self.setWindowTitle, "ui.window.title")
        self.tabs.currentChanged.connect(self._on_tab_changed)

        self.load_from(config)
        self._apply_language()
        self._on_tab_changed(0)

    @property
    def current_config(self) -> Config:
        """The last saved configuration (the widgets may hold unsaved edits)."""
        return self._config

    # -- i18n ---------------------------------------------------------------------------------

    def _t(self, setter: Callable[[str], None], key: str, **params) -> None:
        """Bind a setter to a translation key; re-applied whenever the language changes."""
        def apply(lang: str) -> None:
            setter(tr(key, lang, **params))

        self._bindings.append(apply)
        apply(self._lang)

    def _apply_language(self) -> None:
        self._lang = resolve_language(self._config.language)
        for apply in self._bindings:
            apply(self._lang)

    def _form_row(self, form: QFormLayout, key: str, widget: QWidget) -> None:
        label = QLabel()
        self._t(label.setText, key)
        form.addRow(label, widget)

    def _checkbox(self, key: str) -> QCheckBox:
        box = QCheckBox()
        self._t(box.setText, key)
        return box

    def _spin(self, low: int, high: int, unit_key: str) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(low, high)
        self._t(lambda text: spin.setSuffix(" " + text), unit_key)
        return spin

    def _add_tab(self, page: QWidget, key: str) -> None:
        index = self.tabs.addTab(page, "")
        self._t(lambda text: self.tabs.setTabText(index, text), key)

    # -- tabs ---------------------------------------------------------------------------------

    def _build_status_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.conn_label = QLabel()
        self.conn_label.setWordWrap(True)
        self.conn_label.setTextFormat(Qt.TextFormat.RichText)
        self.state_label = QLabel()
        layout.addWidget(self.conn_label)
        layout.addWidget(self.state_label)

        self.grid = QGridLayout()
        self.grid.setColumnStretch(1, 1)
        holder = QWidget()
        holder_layout = QVBoxLayout(holder)
        holder_layout.addLayout(self.grid)
        holder_layout.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(holder)
        self.no_levels = QLabel()
        self.no_levels.setWordWrap(True)
        self._t(self.no_levels.setText, "ui.status.no_levels")
        layout.addWidget(self.no_levels)
        layout.addWidget(scroll, 1)

        buttons = QHBoxLayout()
        self.test_button, self.reconnect_button, self.quit_button = QPushButton(), QPushButton(), QPushButton()
        self._t(self.test_button.setText, "ui.btn.test_alert")
        self._t(self.reconnect_button.setText, "ui.btn.reconnect")
        self._t(self.quit_button.setText, "ui.btn.quit")
        self.test_button.clicked.connect(self._monitor.send_test_alert)
        self.reconnect_button.clicked.connect(self._monitor.reconnect)
        self.quit_button.clicked.connect(self.request_quit)
        buttons.addWidget(self.test_button)
        buttons.addWidget(self.reconnect_button)
        buttons.addStretch(1)
        buttons.addWidget(self.quit_button)
        layout.addLayout(buttons)
        self._add_tab(page, "ui.tab.status")

    def _build_connection_tab(self) -> None:
        page = QWidget()
        form = QFormLayout(page)
        self.host = QLineEdit()
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self._form_row(form, "ui.conn.host", self.host)
        self._form_row(form, "ui.conn.port", self.port)
        self._form_row(form, "ui.conn.password", self.password)
        for key in ("ui.conn.password_hint", "ui.conn.howto"):
            note = QLabel()
            note.setWordWrap(True)
            note.setEnabled(False)
            self._t(note.setText, key)
            form.addRow(note)
        self._add_tab(page, "ui.tab.connection")

    def _build_monitoring_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.all_inputs, self.selected_inputs = QRadioButton(), QRadioButton()
        self._t(self.all_inputs.setText, "ui.mon.all_inputs")
        self._t(self.selected_inputs.setText, "ui.mon.selected_inputs")
        self.inputs_list = QListWidget()
        self.inputs_hint = QLabel()
        self.inputs_hint.setEnabled(False)
        self._t(self.inputs_hint.setText, "ui.mon.no_inputs")
        self.all_inputs.toggled.connect(lambda: self.inputs_list.setEnabled(self.selected_inputs.isChecked()))
        layout.addWidget(self.all_inputs)
        layout.addWidget(self.selected_inputs)
        layout.addWidget(self.inputs_list, 1)
        layout.addWidget(self.inputs_hint)

        form = QFormLayout()
        self.threshold = QDoubleSpinBox()
        self.threshold.setRange(-120.0, 0.0)
        self.threshold.setDecimals(0)
        self._t(lambda text: self.threshold.setSuffix(" " + text), "ui.unit.db")
        self.window = self._spin(5, 24 * 3600, "ui.unit.s")
        self._form_row(form, "ui.mon.threshold", self.threshold)
        self._form_row(form, "ui.mon.window", self.window)
        layout.addLayout(form)
        self.only_recording = self._checkbox("ui.mon.only_recording")
        self.include_streaming = self._checkbox("ui.mon.include_streaming")
        self.ignore_muted = self._checkbox("ui.mon.ignore_muted")
        for box in (self.only_recording, self.include_streaming, self.ignore_muted):
            layout.addWidget(box)
        self._add_tab(page, "ui.tab.monitoring")

    def _build_alerts_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.notification = self._checkbox("ui.alerts.notification")
        self.sound = self._checkbox("ui.alerts.sound")
        self.speech = self._checkbox("ui.alerts.speech")
        self.notify_recovery = self._checkbox("ui.alerts.notify_recovery")
        form = QFormLayout()
        self.sound_name = QComboBox()
        self.sound_name.addItems(alerts_module.available_sounds())
        self.play_button = QPushButton()
        self._t(self.play_button.setText, "ui.btn.play")
        self.play_button.clicked.connect(self._play_sound)
        sound_row = QWidget()
        row_layout = QHBoxLayout(sound_row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.addWidget(self.sound_name, 1)
        row_layout.addWidget(self.play_button)
        self.voice = QComboBox()
        self.voice.addItem("", "")
        for name in alerts_module.available_voices():
            self.voice.addItem(name, name)
        self._t(lambda text: self.voice.setItemText(0, text), "ui.alerts.voice_default")
        self.repeat = self._spin(10, 24 * 3600, "ui.unit.s")
        self._form_row(form, "ui.alerts.sound_name", sound_row)
        self._form_row(form, "ui.alerts.voice", self.voice)
        self._form_row(form, "ui.alerts.repeat", self.repeat)
        layout.addWidget(self.notification)
        layout.addWidget(self.sound)
        layout.addWidget(self.speech)
        layout.addLayout(form)
        layout.addWidget(self.notify_recovery)
        self.alerts_test_button = QPushButton()
        self._t(self.alerts_test_button.setText, "ui.btn.test_alert")
        self.alerts_test_button.clicked.connect(self._test_alert_with_form)
        layout.addWidget(self.alerts_test_button, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addStretch(1)
        self._add_tab(page, "ui.tab.alerts")

    def _build_healing_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.heal_enabled = self._checkbox("ui.heal.enabled")
        note = QLabel()
        note.setWordWrap(True)
        note.setEnabled(False)
        self._t(note.setText, "ui.heal.note")
        form = QFormLayout()
        self.heal_after = self._spin(1, 3600, "ui.unit.s")
        self.heal_attempts = QSpinBox()
        self.heal_attempts.setRange(0, 20)
        self.heal_cooldown = self._spin(5, 24 * 3600, "ui.unit.s")
        self._form_row(form, "ui.heal.after", self.heal_after)
        self._form_row(form, "ui.heal.attempts", self.heal_attempts)
        self._form_row(form, "ui.heal.cooldown", self.heal_cooldown)
        layout.addWidget(self.heal_enabled)
        layout.addWidget(note)
        layout.addLayout(form)
        layout.addStretch(1)
        self._add_tab(page, "ui.tab.healing")

    def _build_general_tab(self) -> None:
        page = QWidget()
        form = QFormLayout(page)
        self.language = QComboBox()
        self.language.addItem("", "auto")
        self.language.addItem("English", "en")
        self.language.addItem("Русский", "ru")
        self._t(lambda text: self.language.setItemText(0, text), "ui.lang.auto")
        self._form_row(form, "ui.general.language", self.language)
        self._add_tab(page, "ui.tab.general")

    # -- settings <-> widgets -----------------------------------------------------------------

    def load_from(self, config: Config) -> None:
        self.host.setText(config.obs.host)
        self.port.setValue(config.obs.port)
        self.password.clear()
        mon = config.monitor
        self.selected_inputs.setChecked(bool(mon.inputs))
        self.all_inputs.setChecked(not mon.inputs)
        self.inputs_list.setEnabled(bool(mon.inputs))
        self._reload_inputs(checked=set(mon.inputs))
        self.threshold.setValue(mon.silence_threshold_db)
        self.window.setValue(mon.silence_seconds)
        self.only_recording.setChecked(mon.only_while_recording)
        self.include_streaming.setChecked(mon.include_streaming)
        self.ignore_muted.setChecked(mon.ignore_muted)
        al = config.alerts
        self.notification.setChecked(al.notification)
        self.sound.setChecked(al.sound)
        self._select(self.sound_name, al.sound_name, al.sound_name)
        self.speech.setChecked(al.speech)
        self._select(self.voice, al.speech_voice, al.speech_voice)
        self.repeat.setValue(al.repeat_seconds)
        self.notify_recovery.setChecked(al.notify_recovery)
        rem = config.remediation
        self.heal_enabled.setChecked(rem.enabled)
        self.heal_after.setValue(rem.after_seconds)
        self.heal_attempts.setValue(rem.max_attempts)
        self.heal_cooldown.setValue(rem.cooldown_seconds)
        self._select(self.language, config.language, None)
        self.message.clear()

    @staticmethod
    def _select(combo: QComboBox, data: str, add_label: str | None) -> None:
        """Select the item with ``data``; add it first if it is missing (e.g. a sound that vanished)."""
        index = combo.findData(data) if combo.itemData(0) is not None else combo.findText(data)
        if index < 0 and add_label:
            combo.addItem(add_label, data)
            index = combo.count() - 1
        combo.setCurrentIndex(max(index, 0))

    def to_config(self) -> Config:
        cfg = copy.deepcopy(self._config)
        cfg.obs.host = self.host.text().strip() or "localhost"
        cfg.obs.port = self.port.value()
        cfg.monitor.inputs = self._selected_inputs() if self.selected_inputs.isChecked() else []
        cfg.monitor.silence_threshold_db = float(self.threshold.value())
        cfg.monitor.silence_seconds = self.window.value()
        cfg.monitor.only_while_recording = self.only_recording.isChecked()
        cfg.monitor.include_streaming = self.include_streaming.isChecked()
        cfg.monitor.ignore_muted = self.ignore_muted.isChecked()
        cfg.alerts.notification = self.notification.isChecked()
        cfg.alerts.sound = self.sound.isChecked()
        cfg.alerts.sound_name = self.sound_name.currentText()
        cfg.alerts.speech = self.speech.isChecked()
        cfg.alerts.speech_voice = self.voice.currentData() or ""
        cfg.alerts.repeat_seconds = self.repeat.value()
        cfg.alerts.notify_recovery = self.notify_recovery.isChecked()
        cfg.remediation.enabled = self.heal_enabled.isChecked()
        cfg.remediation.after_seconds = self.heal_after.value()
        cfg.remediation.max_attempts = self.heal_attempts.value()
        cfg.remediation.cooldown_seconds = self.heal_cooldown.value()
        cfg.language = self.language.currentData()
        return cfg

    def _selected_inputs(self) -> list[str]:
        return [
            self.inputs_list.item(i).text()
            for i in range(self.inputs_list.count())
            if self.inputs_list.item(i).checkState() == Qt.CheckState.Checked
        ]

    def _reload_inputs(self, checked: set[str] | None = None) -> None:
        """Fill the list from OBS's inputs plus any configured name OBS does not know right now."""
        if checked is None:
            checked = set(self._selected_inputs())
        obs_names = [name for name, _kind in self._monitor.list_inputs()]
        names = obs_names + sorted(checked - set(obs_names))
        self.inputs_list.clear()
        for name in names:
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if name in checked else Qt.CheckState.Unchecked)
            self.inputs_list.addItem(item)
        self._known_inputs = obs_names
        self.inputs_hint.setVisible(not obs_names)

    def save(self) -> bool:
        config = self.to_config()
        problems = config.validate()
        if problems:
            self._show_message(tr("ui.invalid", self._lang, problems="; ".join(problems)), error=True)
            return False
        password = self.password.text()
        if password:
            self._store_password(password)
            self.password.clear()
        self._save_config(config)
        self._config = config
        self._monitor.apply_config(config)
        if password:
            self._monitor.reconnect()
        self._apply_language()
        self._show_message(tr("ui.saved", self._lang), error=False)
        return True

    def _show_message(self, text: str, error: bool) -> None:
        self.message.setStyleSheet(f"color: {RED.name()};" if error else f"color: {GREEN.name()};")
        self.message.setText(text)

    def _play_sound(self) -> None:
        command = alerts_module.sound_command(self.sound_name.currentText())
        if command:
            alerts_module.run_detached(command)

    def _test_alert_with_form(self) -> None:
        alerts_module.AlertDispatcher(self.to_config().alerts, self._lang).send_test()

    # -- live view ----------------------------------------------------------------------------

    def refresh(self, status: Status, levels: dict[str, float | None]) -> None:
        """Render the current state; called several times a second."""
        lang = self._lang
        dot_color = {CONNECTED: GREEN, CONNECTING: AMBER}.get(status.connection, RED).name()
        key = {"connected": "conn.connected", "connecting": "conn.connecting"}.get(status.connection, "conn.disconnected")
        text = f'<span style="color:{dot_color}">●</span> <b>{tr(key, lang)}</b>'
        if status.error:
            text += f"<br>{status.error}"
        self.conn_label.setText(text)
        on, off = tr("ui.state.on", lang), tr("ui.state.off", lang)
        self.state_label.setText(
            f"{tr('ui.status.recording', lang)}: {on if status.recording else off}    "
            f"{tr('ui.status.streaming', lang)}: {on if status.streaming else off}"
        )

        names = sorted(set(levels) | {snap.name for snap in status.inputs})
        self._sync_rows(names)
        self.no_levels.setVisible(not names)
        threshold = self._config.monitor.silence_threshold_db
        unit = tr("ui.unit.db", lang)
        for name in names:
            row = self._rows[name]
            db = levels.get(name)
            state_text, severity = input_state(name, status, self._config, lang)
            row.bar.set_level(db, threshold, lost=severity == "bad")
            row.db.setText("—" if db is None else ("−∞" if db <= SILENCE_FLOOR_DB else f"{db:.0f}") + f" {unit}")
            row.state.setText(state_text)
            row.state.setStyleSheet(SEVERITY_STYLE[severity])

        known = [name for name, _kind in self._monitor.list_inputs()]
        if known != self._known_inputs:
            self._reload_inputs()

    def _sync_rows(self, names: list[str]) -> None:
        if names == sorted(self._rows):
            return
        for row in self._rows.values():
            for widget in row.widgets():
                self.grid.removeWidget(widget)
                widget.deleteLater()
        self._rows = {}
        for index, name in enumerate(names):
            row = self._rows[name] = _Row()
            row.name.setText(name)
            for column, widget in enumerate(row.widgets()):
                self.grid.addWidget(widget, index, column)

    # -- window lifecycle -----------------------------------------------------------------------

    def _on_tab_changed(self, index: int) -> None:
        self.bottom.setVisible(index != 0)

    def request_quit(self) -> None:
        self._quitting = True
        self.quit_requested.emit()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if self._quitting:
            event.accept()
        else:  # closing the window keeps the watchdog running in the menu bar
            event.ignore()
            self.hide()
