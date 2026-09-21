"""Alert delivery on macOS: notification centre, sound, speech.

Every channel is a subprocess started without a shell, so alert text can never be interpreted
as a command. The runner is injectable so tests never make noise.
"""

import re
import subprocess
import threading
import time
from collections.abc import Callable
from pathlib import Path

from obs_keeper.config import AlertConfig
from obs_keeper.detector import LOST, RECOVERED, REMEDIATE, REMINDER, Transition
from obs_keeper.i18n import format_duration, tr

SOUNDS_DIR = Path("/System/Library/Sounds")
_VOICE_RE = re.compile(r"^[\w][\w .()-]*$")

Runner = Callable[[list[str]], None]


def run_detached(command: list[str]) -> None:
    def target() -> None:
        try:
            subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60, check=False)
        except (OSError, subprocess.SubprocessError):
            pass  # alerts are best effort; a missing binary must not crash the watchdog

    threading.Thread(target=target, daemon=True).start()


class SoundPlayer:
    """Plays a sound file over and over for a number of seconds; can be cut short.

    ``afplay`` has no loop option, and a single macOS system sound lasts about a second, which is
    easy to miss while a lecture is playing. A new ``play`` replaces the previous one.
    """

    def __init__(self, popen=subprocess.Popen, clock=time.monotonic):
        self._popen = popen
        self._clock = clock
        self._cancel = threading.Event()
        self._lock = threading.Lock()

    def play(self, command: list[str], seconds: float) -> None:
        with self._lock:
            self._cancel.set()  # stop the previous loop
            cancel = self._cancel = threading.Event()
        threading.Thread(target=self._loop, args=(command, seconds, cancel), daemon=True).start()

    def stop(self) -> None:
        with self._lock:
            self._cancel.set()

    def _loop(self, command: list[str], seconds: float, cancel: threading.Event) -> None:
        deadline = self._clock() + seconds
        while not cancel.is_set() and self._clock() < deadline:
            try:
                proc = self._popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except OSError:
                return  # best effort: no afplay, no sound
            while proc.poll() is None:
                if cancel.wait(0.05):
                    proc.terminate()
                    break
            proc.wait()


class _RunnerSound:
    """Plays once through the plain command runner (used by tests and as a fallback)."""

    def __init__(self, runner: "Runner"):
        self._runner = runner

    def play(self, command: list[str], seconds: float) -> None:
        self._runner(command)

    def stop(self) -> None:
        pass


def available_sounds() -> list[str]:
    """Names of macOS system sounds (``Sosumi``, ``Glass``, ...)."""
    try:
        return sorted(p.stem for p in SOUNDS_DIR.glob("*.aiff"))
    except OSError:
        return []


_VOICE_LINE_RE = re.compile(r"^(.+?)\s{2,}[a-z]{2}_[A-Z]{2}\b")


def available_voices() -> list[str]:
    """Names of installed macOS voices (``say -v '?'``); empty if the command is unavailable."""
    try:
        out = subprocess.run(["say", "-v", "?"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    names = (m.group(1).strip() for m in map(_VOICE_LINE_RE.match, out.splitlines()) if m)
    return sorted(set(names))


def notification_command(title: str, message: str) -> list[str]:
    # Text is passed as argv, never spliced into the AppleScript source.
    return [
        "osascript",
        "-e", "on run argv",
        "-e", "display notification (item 1 of argv) with title (item 2 of argv)",
        "-e", "end run",
        message, title,
    ]


def sound_command(sound_name: str) -> list[str] | None:
    if sound_name not in available_sounds():
        return None
    return ["afplay", str(SOUNDS_DIR / f"{sound_name}.aiff")]


def speech_command(text: str, voice: str) -> list[str]:
    command = ["say"]
    if voice and _VOICE_RE.match(voice):
        command += ["-v", voice]
    return command + ["--", text]


class AlertDispatcher:
    def __init__(self, config: AlertConfig, language: str, runner: Runner = run_detached, sound=None):
        self.config = config
        self.language = language
        self._run = runner
        self._sound = sound or _RunnerSound(runner)

    @classmethod
    def create(cls, config: AlertConfig, language: str) -> "AlertDispatcher":
        """The real thing: notifications and speech via subprocesses, a looping sound player."""
        return cls(config, language, run_detached, SoundPlayer())

    def stop_sound(self) -> None:
        self._sound.stop()

    def handle(self, transition: Transition, max_attempts: int = 0) -> None:
        """Deliver the alert that corresponds to a detector transition."""
        lang = self.language
        duration = format_duration(transition.silent_for, lang)
        if transition.kind in (LOST, REMINDER):
            title = tr("alert.lost.title" if transition.kind == LOST else "alert.reminder.title", lang)
            body = tr(f"alert.lost.{transition.reason}", lang, input=transition.input_name, duration=duration)
            self.send(title, body, loud=True)
        elif transition.kind == RECOVERED:
            self.stop_sound()
            if self.config.notify_recovery:
                body = tr("alert.recovered.body", lang, input=transition.input_name, duration=duration)
                self.send(tr("alert.recovered.title", lang), body, loud=False)
        elif transition.kind == REMEDIATE:
            body = tr(
                "alert.remediate.body", lang,
                input=transition.input_name, attempt=transition.attempt, max_attempts=max_attempts,
            )
            self.send(tr("alert.remediate.title", lang), body, loud=False)

    def send_test(self) -> None:
        self.send(tr("alert.test.title", self.language), tr("alert.test.body", self.language), loud=True)

    def send(self, title: str, message: str, loud: bool) -> None:
        cfg = self.config
        if cfg.notification:
            self._run(notification_command(title, message))
        if loud and cfg.sound:
            command = sound_command(cfg.sound_name)
            if command:
                self._sound.play(command, cfg.sound_seconds)
        if loud and cfg.speech:
            self._run(speech_command(f"{title}. {message}", cfg.speech_voice))
