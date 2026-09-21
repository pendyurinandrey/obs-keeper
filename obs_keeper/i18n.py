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
