"""Silence detection as a pure state machine: no I/O, no threads, no clock.

Callers pass ``now`` (any monotonic float, seconds). Signal is tracked as "time of the last
sample above the threshold", so an input that stops reporting levels altogether is caught by
the very same rule as one that reports silence (``reason == "no_data"``).
"""

from dataclasses import dataclass

from obs_keeper.config import MonitorConfig, RemediationConfig

# OBS reports levels many times a second; a gap this long means the input stopped reporting.
NO_DATA_AFTER_SECONDS = 3.0

LOST = "lost"
REMINDER = "reminder"
RECOVERED = "recovered"
REMEDIATE = "remediate"

REASON_SILENCE = "silence"
REASON_NO_DATA = "no_data"


@dataclass(frozen=True)
class Transition:
    kind: str  # LOST | REMINDER | RECOVERED | REMEDIATE
    input_name: str
    silent_for: float
    reason: str = REASON_SILENCE
    attempt: int = 0  # REMEDIATE only: 1-based attempt number


@dataclass(frozen=True)
class InputSnapshot:
    name: str
    peak_db: float | None
    silent_for: float
    muted: bool
    lost: bool
    reason: str


@dataclass
class _Watch:
    name: str
    last_signal_at: float
    last_sample_at: float | None = None
    last_db: float | None = None
    muted: bool = False
    lost_since: float | None = None
    last_alert_at: float = 0.0
    attempts: int = 0
    last_attempt_at: float | None = None


class SilenceDetector:
    def __init__(self, monitor: MonitorConfig, repeat_seconds: int, remediation: RemediationConfig):
        self._monitor = monitor
        self._repeat = repeat_seconds
        self._remediation = remediation
        self._watches: dict[str, _Watch] = {}
        self._muted: set[str] = set()  # known even before a watch exists (mute state arrives on connect)
        self._active = False

    @property
    def active(self) -> bool:
        return self._active

    def configure(self, monitor: MonitorConfig, repeat_seconds: int, remediation: RemediationConfig, now: float) -> None:
        """Apply new settings without losing per-input state of inputs that stay watched."""
        self._monitor = monitor
        self._repeat = repeat_seconds
        self._remediation = remediation
        if monitor.inputs:
            self._watches = {n: w for n, w in self._watches.items() if n in monitor.inputs}
            for name in monitor.inputs:
                self._watches.setdefault(name, self._new_watch(name, now))

    def set_active(self, active: bool, now: float) -> None:
        """Turn watching on/off (recording started/stopped). Turning on starts a fresh grace period."""
        if active and not self._active:
            self._watches = {}
            for name in self._monitor.inputs:
                self._watches[name] = self._new_watch(name, now)
        elif not active:
            self._watches = {}
        self._active = active

    def on_sample(self, name: str, peak_db: float, now: float) -> list[Transition]:
        """Feed one level sample. Returns ``recovered`` if a lost input just came back."""
        if not self._active or not self._is_watched(name):
            return []
        watch = self._watches.get(name)
        if watch is None:
            watch = self._watches[name] = self._new_watch(name, now)
        watch.last_sample_at = now
        watch.last_db = peak_db
        if peak_db <= self._monitor.silence_threshold_db:
            return []
        transitions = []
        if watch.lost_since is not None:
            transitions.append(Transition(RECOVERED, name, now - watch.last_signal_at))
            self._clear_lost(watch)
        watch.last_signal_at = now
        return transitions

    def set_muted(self, name: str, muted: bool, now: float) -> None:
        (self._muted.add if muted else self._muted.discard)(name)
        watch = self._watches.get(name)
        if watch is not None:
            watch.muted = muted
            if muted:
                watch.last_signal_at = now

    def evaluate(self, now: float) -> list[Transition]:
        """Advance timers; call about once a second."""
        if not self._active:
            return []
        transitions: list[Transition] = []
        for watch in self._watches.values():
            if watch.muted and self._monitor.ignore_muted:
                watch.last_signal_at = now
                self._clear_lost(watch)
                continue
            silent_for = now - watch.last_signal_at
            reason = self._reason(watch, now)
            if watch.lost_since is None:
                if silent_for >= self._monitor.silence_seconds:
                    watch.lost_since = now
                    watch.last_alert_at = now
                    transitions.append(Transition(LOST, watch.name, silent_for, reason))
                continue
            if now - watch.last_alert_at >= self._repeat:
                watch.last_alert_at = now
                transitions.append(Transition(REMINDER, watch.name, silent_for, reason))
            if self._should_remediate(watch, now):
                watch.attempts += 1
                watch.last_attempt_at = now
                transitions.append(Transition(REMEDIATE, watch.name, silent_for, reason, attempt=watch.attempts))
        return transitions

    def snapshot(self, now: float) -> list[InputSnapshot]:
        return [
            InputSnapshot(
                name=w.name,
                peak_db=w.last_db,
                silent_for=now - w.last_signal_at,
                muted=w.muted,
                lost=w.lost_since is not None,
                reason=self._reason(w, now),
            )
            for w in self._watches.values()
        ]

    def any_lost(self) -> bool:
        return any(w.lost_since is not None for w in self._watches.values())

    def _new_watch(self, name: str, now: float) -> _Watch:
        return _Watch(name, last_signal_at=now, muted=name in self._muted)

    def _is_watched(self, name: str) -> bool:
        return not self._monitor.inputs or name in self._monitor.inputs

    def _reason(self, watch: _Watch, now: float) -> str:
        if watch.last_sample_at is None or now - watch.last_sample_at > NO_DATA_AFTER_SECONDS:
            return REASON_NO_DATA
        return REASON_SILENCE

    def _should_remediate(self, watch: _Watch, now: float) -> bool:
        cfg = self._remediation
        if not cfg.enabled or watch.lost_since is None or watch.attempts >= cfg.max_attempts:
            return False
        if now - watch.lost_since < cfg.after_seconds:
            return False
        return watch.last_attempt_at is None or now - watch.last_attempt_at >= cfg.cooldown_seconds

    @staticmethod
    def _clear_lost(watch: _Watch) -> None:
        watch.lost_since = None
        watch.attempts = 0
        watch.last_attempt_at = None
