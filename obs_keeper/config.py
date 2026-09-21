"""Settings stored as JSON; the OBS password is kept elsewhere (see ``credentials``)."""

import dataclasses
import json
import os
import sys
import typing
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_ENV = "OBS_KEEPER_CONFIG"


@dataclass
class ObsConfig:
    host: str = "localhost"
    port: int = 4455


@dataclass
class MonitorConfig:
    # Input names to watch. Empty = every input that has reported levels since watching began.
    inputs: list[str] = field(default_factory=list)
    silence_threshold_db: float = -70.0
    silence_seconds: int = 180
    warn_seconds: int = 20  # the icon turns red after this much silence (no sound yet); capped by silence_seconds
    only_while_recording: bool = True
    include_streaming: bool = False
    ignore_muted: bool = True


@dataclass
class AlertConfig:
    notification: bool = True
    sound: bool = True
    sound_name: str = "Sosumi"
    sound_seconds: int = 15  # the sound is repeated for this long, so it cuts through a lecture
    speech: bool = False
    speech_voice: str = ""
    repeat_seconds: int = 120
    notify_recovery: bool = True


@dataclass
class RemediationConfig:
    enabled: bool = False
    after_seconds: int = 30
    max_attempts: int = 2
    cooldown_seconds: int = 300


@dataclass
class Config:
    obs: ObsConfig = field(default_factory=ObsConfig)
    monitor: MonitorConfig = field(default_factory=MonitorConfig)
    alerts: AlertConfig = field(default_factory=AlertConfig)
    remediation: RemediationConfig = field(default_factory=RemediationConfig)
    language: str = "auto"  # "auto" | "en" | "ru"

    def validate(self) -> list[str]:
        """Human-readable problems; empty when the config is usable."""
        problems = []
        if not 1 <= self.obs.port <= 65535:
            problems.append("obs.port must be 1..65535")
        if self.monitor.silence_seconds < 5:
            problems.append("monitor.silence_seconds must be at least 5")
        if self.monitor.warn_seconds < 1:
            problems.append("monitor.warn_seconds must be at least 1")
        if not -120.0 <= self.monitor.silence_threshold_db <= 0.0:
            problems.append("monitor.silence_threshold_db must be between -120 and 0")
        if not 1 <= self.alerts.sound_seconds <= 300:
            problems.append("alerts.sound_seconds must be 1..300")
        if self.alerts.repeat_seconds < 10:
            problems.append("alerts.repeat_seconds must be at least 10")
        if self.remediation.max_attempts < 0:
            problems.append("remediation.max_attempts must not be negative")
        if self.language not in ("auto", "en", "ru"):
            problems.append("language must be auto, en or ru")
        return problems


def config_path() -> Path:
    override = os.environ.get(CONFIG_ENV)
    if override:
        return Path(override).expanduser()
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "obs-keeper" / "config.json"


def _build(cls, data: object):
    """Build dataclass ``cls`` from ``data``, ignoring unknown keys and bad types."""
    instance = cls()
    if not isinstance(data, dict):
        return instance
    hints = typing.get_type_hints(cls)
    for f in dataclasses.fields(cls):
        if f.name not in data:
            continue
        value, hint = data[f.name], hints[f.name]
        if dataclasses.is_dataclass(hint):
            setattr(instance, f.name, _build(hint, value))
        elif hint is float and isinstance(value, (int, float)) and not isinstance(value, bool):
            setattr(instance, f.name, float(value))
        elif hint == list[str]:
            if isinstance(value, list) and all(isinstance(v, str) for v in value):
                setattr(instance, f.name, list(value))
        elif isinstance(value, hint) and not (hint is int and isinstance(value, bool)):
            setattr(instance, f.name, value)
    return instance


def config_from_dict(data: object) -> Config:
    return _build(Config, data)


def load_config(path: Path | None = None) -> Config:
    """Load the config; a missing or corrupt file yields defaults."""
    path = path or config_path()
    try:
        return config_from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return Config()


def save_config(config: Config, path: Path | None = None) -> Path:
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(dataclasses.asdict(config), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)
    return path
