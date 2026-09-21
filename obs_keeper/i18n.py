"""Translations (English, Russian) for alerts, CLI and UI.

Plain dictionaries instead of Qt ``.ts`` files: alerts must be translated without Qt, and a test
checks that both languages define the same keys. Use ``{name}`` placeholders.
"""

import os
import subprocess
import sys

LANGUAGES = ("en", "ru")
DEFAULT_LANGUAGE = "en"

STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "alert.lost.title": "OBS: audio lost",
        "alert.lost.silence": "“{input}” has been silent for {duration}.",
        "alert.lost.no_data": "“{input}” has stopped sending audio for {duration}.",
        "alert.reminder.title": "OBS: audio is still missing",
        "alert.recovered.title": "OBS: audio is back",
        "alert.recovered.body": "“{input}” is producing sound again after {duration}.",
        "alert.remediate.title": "OBS: restarting the source",
        "alert.remediate.body": "Restarting “{input}” (attempt {attempt} of {max_attempts}).",
        "alert.test.title": "OBS Keeper: test alert",
        "alert.test.body": "If you can see and hear this, alerts work.",
        "duration.seconds": "{s} s",
        "duration.minutes": "{m} min {s:02d} s",
        "duration.hours": "{h} h {m:02d} min",
        "conn.connected": "Connected to OBS",
        "conn.connecting": "Connecting to OBS…",
        "conn.disconnected": "OBS is not reachable",
        "conn.error.refused": "Connection refused. Is OBS running with the WebSocket server enabled (Tools → WebSocket Server Settings)?",
        "conn.error.auth": "OBS rejected the password (or closed the connection).",
        "conn.error.other": "Cannot talk to OBS: {detail}",
        "cli.no_password": "No password set. Run `obs-keeper set-password` or export OBS_KEEPER_PASSWORD.",
        "cli.password_prompt": "OBS WebSocket password: ",
        "cli.password_saved": "Password saved to the system keychain.",
        "cli.watching": "Watching OBS. Press Ctrl+C to stop.",
        "cli.config_problems": "Invalid configuration:",
        "ui.window.title": "OBS Keeper",
        "ui.tab.status": "Status",
        "ui.tab.connection": "Connection",
        "ui.tab.monitoring": "Monitoring",
        "ui.tab.alerts": "Alerts",
        "ui.tab.healing": "Self-healing",
        "ui.tab.general": "General",
        "ui.status.connection": "Connection",
        "ui.status.recording": "Recording",
        "ui.status.streaming": "Streaming",
        "ui.state.on": "on",
        "ui.state.off": "off",
        "ui.status.no_levels": "No audio levels yet. They appear as soon as OBS has an active audio source.",
        "ui.input.watching": "Watching",
        "ui.input.waiting": "Waiting for recording",
        "ui.input.muted": "Muted",
        "ui.input.not_watched": "Not watched",
        "ui.input.quiet": "Quiet for {duration}",
        "ui.input.lost": "SILENT for {duration}",
        "ui.input.no_data": "NO DATA for {duration}",
        "ui.btn.test_alert": "Send test alert",
        "ui.btn.reconnect": "Reconnect",
        "ui.btn.quit": "Quit",
        "ui.btn.save": "Save",
        "ui.btn.revert": "Revert",
        "ui.btn.refresh": "Refresh list",
        "ui.btn.play": "Play",
        "ui.btn.reveal": "Show in Finder",
        "ui.conn.host": "Host",
        "ui.conn.port": "Port",
        "ui.conn.password": "Password",
        "ui.conn.password_hint": "Stored in the system keychain. Leave empty to keep the current password.",
        "ui.conn.howto": "In OBS: Tools → WebSocket Server Settings → enable the server and set a password.",
        "ui.mon.all_inputs": "Watch every input that reports audio",
        "ui.mon.selected_inputs": "Watch only the inputs ticked below",
        "ui.mon.no_inputs": "Connect to OBS to load its inputs.",
        "ui.mon.threshold": "Silence threshold",
        "ui.mon.warn_window": "Icon turns red after silence lasts",
        "ui.mon.window": "Sound the alert after silence lasts",
        "ui.mon.only_recording": "Watch only while OBS is recording",
        "ui.mon.include_streaming": "Also watch while streaming",
        "ui.mon.ignore_muted": "Ignore inputs muted in OBS",
        "ui.alerts.notification": "Show a notification",
        "ui.alerts.sound": "Play a sound",
        "ui.alerts.sound_name": "Sound",
        "ui.alerts.sound_seconds": "Keep the sound going for",
        "ui.alerts.speech": "Speak the alert aloud",
        "ui.alerts.voice": "Voice",
        "ui.alerts.voice_default": "System default",
        "ui.alerts.repeat": "Repeat every",
        "ui.alerts.notify_recovery": "Notify when sound returns",
        "ui.heal.enabled": "Restart the source automatically when audio is lost",
        "ui.heal.note": "Experimental: hides and re-shows the source in its scenes. Works only for inputs that are scene items (for example macOS Screen Capture).",
        "ui.heal.after": "First attempt after",
        "ui.heal.attempts": "Attempts per outage",
        "ui.heal.cooldown": "Pause between attempts",
        "ui.general.language": "Language",
        "ui.general.config_file": "Settings file",
        "ui.lang.auto": "Automatic",
        "ui.unit.s": "s",
        "ui.unit.db": "dB",
        "ui.saved": "Settings saved.",
        "ui.unsaved": "Unsaved changes: press Save.",
        "ui.invalid": "Cannot save: {problems}",
        "ui.tray.watching": "OBS Keeper: watching the audio",
        "ui.tray.idle": "OBS Keeper: connected, OBS is not recording",
        "ui.tray.alert": "OBS Keeper: AUDIO IS LOST",
        "ui.tray.warning": "OBS Keeper: no sound for a while",
        "ui.tray.offline": "OBS Keeper: not connected to OBS",
        "ui.menu.open": "Open OBS Keeper",
        "ui.menu.quit": "Quit OBS Keeper",
        "ui.already_running": "OBS Keeper is already running (see the icon in the menu bar).",
        "ui.missing_pyside": "The UI needs PySide6. Install it with: pip install -e \".[ui]\"",
    },
    "ru": {
        "alert.lost.title": "OBS: пропал звук",
        "alert.lost.silence": "«{input}» молчит уже {duration}.",
        "alert.lost.no_data": "«{input}» перестал передавать звук {duration} назад.",
        "alert.reminder.title": "OBS: звука по-прежнему нет",
        "alert.recovered.title": "OBS: звук вернулся",
        "alert.recovered.body": "«{input}» снова звучит, пропажа длилась {duration}.",
        "alert.remediate.title": "OBS: перезапуск источника",
        "alert.remediate.body": "Перезапускаю «{input}» (попытка {attempt} из {max_attempts}).",
        "alert.test.title": "OBS Keeper: проверка оповещений",
        "alert.test.body": "Если вы это видите и слышите, оповещения работают.",
        "duration.seconds": "{s} с",
        "duration.minutes": "{m} мин {s:02d} с",
        "duration.hours": "{h} ч {m:02d} мин",
        "conn.connected": "Подключено к OBS",
        "conn.connecting": "Подключение к OBS…",
        "conn.disconnected": "OBS недоступен",
        "conn.error.refused": "Соединение отклонено. OBS запущен и включён ли сервер WebSocket (Инструменты → Настройки сервера WebSocket)?",
        "conn.error.auth": "OBS отклонил пароль (или закрыл соединение).",
        "conn.error.other": "Не удаётся связаться с OBS: {detail}",
        "cli.no_password": "Пароль не задан. Выполните `obs-keeper set-password` или задайте OBS_KEEPER_PASSWORD.",
        "cli.password_prompt": "Пароль WebSocket OBS: ",
        "cli.password_saved": "Пароль сохранён в связке ключей системы.",
        "cli.watching": "Слежу за OBS. Для выхода нажмите Ctrl+C.",
        "cli.config_problems": "Некорректная конфигурация:",
        "ui.window.title": "OBS Keeper",
        "ui.tab.status": "Состояние",
        "ui.tab.connection": "Подключение",
        "ui.tab.monitoring": "Наблюдение",
        "ui.tab.alerts": "Оповещения",
        "ui.tab.healing": "Самолечение",
        "ui.tab.general": "Общее",
        "ui.status.connection": "Подключение",
        "ui.status.recording": "Запись",
        "ui.status.streaming": "Трансляция",
        "ui.state.on": "идёт",
        "ui.state.off": "нет",
        "ui.status.no_levels": "Уровней звука пока нет. Они появятся, как только в OBS будет активный источник звука.",
        "ui.input.watching": "Слежу",
        "ui.input.waiting": "Жду начала записи",
        "ui.input.muted": "Заглушён",
        "ui.input.not_watched": "Не отслеживается",
        "ui.input.quiet": "Тихо уже {duration}",
        "ui.input.lost": "ТИШИНА {duration}",
        "ui.input.no_data": "НЕТ ДАННЫХ {duration}",
        "ui.btn.test_alert": "Проверить оповещение",
        "ui.btn.reconnect": "Переподключиться",
        "ui.btn.quit": "Выход",
        "ui.btn.save": "Сохранить",
        "ui.btn.revert": "Отменить",
        "ui.btn.refresh": "Обновить список",
        "ui.btn.play": "Прослушать",
        "ui.btn.reveal": "Показать в Finder",
        "ui.conn.host": "Хост",
        "ui.conn.port": "Порт",
        "ui.conn.password": "Пароль",
        "ui.conn.password_hint": "Хранится в связке ключей системы. Оставьте пустым, чтобы не менять текущий.",
        "ui.conn.howto": "В OBS: Инструменты → Настройки сервера WebSocket → включите сервер и задайте пароль.",
        "ui.mon.all_inputs": "Следить за каждым входом со звуком",
        "ui.mon.selected_inputs": "Следить только за отмеченными ниже",
        "ui.mon.no_inputs": "Подключитесь к OBS, чтобы загрузить список входов.",
        "ui.mon.threshold": "Порог тишины",
        "ui.mon.warn_window": "Значок краснеет, если тишина длится",
        "ui.mon.window": "Включить сигнал, если тишина длится",
        "ui.mon.only_recording": "Следить только во время записи",
        "ui.mon.include_streaming": "Следить и во время трансляции",
        "ui.mon.ignore_muted": "Игнорировать входы, заглушённые в OBS",
        "ui.alerts.notification": "Показывать уведомление",
        "ui.alerts.sound": "Проигрывать звук",
        "ui.alerts.sound_name": "Звук",
        "ui.alerts.sound_seconds": "Играть сигнал",
        "ui.alerts.speech": "Произносить оповещение голосом",
        "ui.alerts.voice": "Голос",
        "ui.alerts.voice_default": "Системный по умолчанию",
        "ui.alerts.repeat": "Повторять каждые",
        "ui.alerts.notify_recovery": "Сообщать, когда звук вернулся",
        "ui.heal.enabled": "Автоматически перезапускать источник при пропаже звука",
        "ui.heal.note": "Экспериментально: скрывает и снова показывает источник в его сценах. Работает только для входов, которые есть в сценах (например, macOS Screen Capture).",
        "ui.heal.after": "Первая попытка через",
        "ui.heal.attempts": "Попыток на один сбой",
        "ui.heal.cooldown": "Пауза между попытками",
        "ui.general.language": "Язык",
        "ui.general.config_file": "Файл настроек",
        "ui.lang.auto": "Автоматически",
        "ui.unit.s": "с",
        "ui.unit.db": "дБ",
        "ui.saved": "Настройки сохранены.",
        "ui.unsaved": "Есть несохранённые изменения: нажмите «Сохранить».",
        "ui.invalid": "Не удалось сохранить: {problems}",
        "ui.tray.watching": "OBS Keeper: слежу за звуком",
        "ui.tray.idle": "OBS Keeper: подключён, запись в OBS не идёт",
        "ui.tray.alert": "OBS Keeper: ПРОПАЛ ЗВУК",
        "ui.tray.warning": "OBS Keeper: звука давно нет",
        "ui.tray.offline": "OBS Keeper: нет связи с OBS",
        "ui.menu.open": "Открыть OBS Keeper",
        "ui.menu.quit": "Выйти из OBS Keeper",
        "ui.already_running": "OBS Keeper уже запущен (см. значок в строке меню).",
        "ui.missing_pyside": "Для интерфейса нужен PySide6. Установите: pip install -e \".[ui]\"",
    },
}


def system_language() -> str:
    """Best guess of the user's UI language: ``"ru"`` if their locale is Russian, else ``"en"``."""
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(var, "")
        if value:
            return "ru" if value.lower().startswith("ru") else "en"
    if sys.platform == "darwin":
        try:
            out = subprocess.run(
                ["defaults", "read", "-g", "AppleLanguages"], capture_output=True, text=True, timeout=3
            ).stdout
            first = next((line.strip(' ",()') for line in out.splitlines() if line.strip(' ",()')), "")
            return "ru" if first.lower().startswith("ru") else "en"
        except (OSError, subprocess.SubprocessError):
            pass
    return DEFAULT_LANGUAGE


def resolve_language(setting: str) -> str:
    """Map the config value (``auto``/``en``/``ru``) to a concrete language."""
    return setting if setting in LANGUAGES else system_language()


def tr(key: str, language: str, **params) -> str:
    text = STRINGS.get(language, STRINGS[DEFAULT_LANGUAGE]).get(key) or STRINGS[DEFAULT_LANGUAGE][key]
    return text.format(**params) if params else text


def format_duration(seconds: float, language: str) -> str:
    total = int(round(seconds))
    if total < 60:
        return tr("duration.seconds", language, s=total)
    if total < 3600:
        return tr("duration.minutes", language, m=total // 60, s=total % 60)
    return tr("duration.hours", language, h=total // 3600, m=total % 3600 // 60)
